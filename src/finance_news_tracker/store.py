from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article, ScoreResult


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff_iso(recency_hours: int) -> str:
    """ISO cutoff for recency filters. All timestamps are stored UTC (+00:00),
    so lexicographic comparison against this string is valid."""
    return (datetime.now(timezone.utc) - timedelta(hours=recency_hours)).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class Store:
    def __init__(
        self,
        db_path: Path,
        *,
        legacy_provider: str = "deepseek",
        legacy_model: str = "deepseek-chat",
    ):
        self.db_path = db_path
        self.legacy_provider = legacy_provider
        self.legacy_model = legacy_model
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT,
                    summary TEXT,
                    content_hash TEXT NOT NULL UNIQUE,
                    raw_excerpt TEXT,
                    collected_at TEXT NOT NULL,
                    scored INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'deepseek',
                    model TEXT NOT NULL DEFAULT 'deepseek-chat',
                    relevance_score INTEGER NOT NULL,
                    fx_channel TEXT,
                    likely_usdjpy_direction TEXT,
                    confidence TEXT,
                    summary TEXT,
                    why_it_matters TEXT,
                    source_citation TEXT,
                    model_raw TEXT,
                    scored_at TEXT NOT NULL,
                    FOREIGN KEY (article_id) REFERENCES articles(id),
                    UNIQUE(article_id, provider, model)
                );

                CREATE TABLE IF NOT EXISTS summary_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'deepseek',
                    model TEXT NOT NULL DEFAULT 'deepseek-chat',
                    article_count INTEGER,
                    top_score INTEGER,
                    body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    markdown_path TEXT,
                    docx_path TEXT,
                    email_sent INTEGER DEFAULT 0,
                    email_recipients TEXT,
                    error_message TEXT,
                    source_count INTEGER,
                    story_count INTEGER,
                    llm_model TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_articles_scored
                    ON articles(scored);
                CREATE INDEX IF NOT EXISTS idx_scores_relevance
                    ON scores(relevance_score DESC);
                CREATE INDEX IF NOT EXISTS idx_run_history_started
                    ON run_history(started_at DESC);
                """
            )
            self._migrate_scores_if_needed(conn)
            self._migrate_summary_runs_if_needed(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scores_provider_model_relevance
                    ON scores(provider, model, relevance_score DESC)
                """
            )

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def _has_real_db_backup(self) -> bool:
        """Require a visible backup before rebuilding a real tracker DB.

        中文注解：真实 `data/tracker.db` 重建前需要用户先备份，测试库不强制。
        """
        if self.db_path.name != "tracker.db":
            return True
        backup_patterns = [
            f"{self.db_path.name}.bak*",
            f"{self.db_path.stem}_backup*.db",
            f"{self.db_path.stem}.backup*.db",
        ]
        return any(
            candidate.exists()
            for pattern in backup_patterns
            for candidate in self.db_path.parent.glob(pattern)
        )

    def _migrate_scores_if_needed(self, conn: sqlite3.Connection) -> None:
        columns = self._table_columns(conn, "scores")
        if {"provider", "model"}.issubset(columns):
            return

        existing_count = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()["c"]
        if existing_count and not self._has_real_db_backup():
            raise RuntimeError(
                "scores table migration requires a data/tracker.db backup first. "
                "Create a backup next to the DB before reopening the tracker."
            )

        conn.executescript(
            """
            CREATE TABLE scores_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                relevance_score INTEGER NOT NULL,
                fx_channel TEXT,
                likely_usdjpy_direction TEXT,
                confidence TEXT,
                summary TEXT,
                why_it_matters TEXT,
                source_citation TEXT,
                model_raw TEXT,
                scored_at TEXT NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles(id),
                UNIQUE(article_id, provider, model)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO scores_new
                (id, article_id, provider, model, relevance_score, fx_channel,
                 likely_usdjpy_direction, confidence, summary, why_it_matters,
                 source_citation, model_raw, scored_at)
            SELECT id, article_id, ?, ?, relevance_score, fx_channel,
                   likely_usdjpy_direction, confidence, summary, why_it_matters,
                   source_citation, model_raw, scored_at
            FROM scores
            """,
            (self.legacy_provider, self.legacy_model),
        )
        conn.executescript(
            """
            DROP TABLE scores;
            ALTER TABLE scores_new RENAME TO scores;
            CREATE INDEX IF NOT EXISTS idx_scores_relevance
                ON scores(relevance_score DESC);
            CREATE INDEX IF NOT EXISTS idx_scores_provider_model_relevance
                ON scores(provider, model, relevance_score DESC);
            """
        )

    def _migrate_summary_runs_if_needed(self, conn: sqlite3.Connection) -> None:
        columns = self._table_columns(conn, "summary_runs")
        if "provider" not in columns:
            provider = self.legacy_provider.replace("'", "''")
            conn.execute(
                f"ALTER TABLE summary_runs ADD COLUMN provider TEXT NOT NULL DEFAULT '{provider}'"
            )
        if "model" not in columns:
            model = self.legacy_model.replace("'", "''")
            conn.execute(
                f"ALTER TABLE summary_runs ADD COLUMN model TEXT NOT NULL DEFAULT '{model}'"
            )

    def upsert_article(self, article: Article) -> tuple[int, bool]:
        """Insert article if new. Returns (id, is_new)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM articles WHERE content_hash = ?",
                (article.content_hash,),
            ).fetchone()
            if row:
                return int(row["id"]), False

            published = (
                article.published_at.isoformat() if article.published_at else None
            )
            cur = conn.execute(
                """
                INSERT INTO articles
                    (source, title, url, published_at, summary, content_hash,
                     raw_excerpt, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.source,
                    article.title,
                    article.url,
                    published,
                    article.summary,
                    article.content_hash,
                    article.raw_excerpt,
                    _utc_now_iso(),
                ),
            )
            return int(cur.lastrowid), True

    def get_existing_hashes(self) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT content_hash FROM articles").fetchall()
        return {row["content_hash"] for row in rows}

    def get_unscored_articles(self) -> list[tuple[Article, int]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, source, title, url, published_at, summary,
                       content_hash, raw_excerpt
                FROM articles
                WHERE scored = 0
                ORDER BY published_at DESC, collected_at DESC
                """
            ).fetchall()

        result: list[tuple[Article, int]] = []
        for row in rows:
            article = Article(
                source=row["source"],
                title=row["title"],
                url=row["url"],
                published_at=_parse_dt(row["published_at"]),
                summary=row["summary"] or "",
                content_hash=row["content_hash"],
                raw_excerpt=row["raw_excerpt"] or "",
            )
            result.append((article, int(row["id"])))
        return result

    def get_all_articles_for_scoring(self) -> list[tuple[Article, int]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, source, title, url, published_at, summary,
                       content_hash, raw_excerpt
                FROM articles
                ORDER BY published_at DESC, collected_at DESC
                """
            ).fetchall()
        return self._rows_to_articles(rows)

    def get_unscored_for(self, provider: str, model: str) -> list[tuple[Article, int]]:
        if not provider or not model:
            raise ValueError("provider and model are required for provider-aware scoring")
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.summary,
                       a.content_hash, a.raw_excerpt
                FROM articles a
                LEFT JOIN scores s
                    ON s.article_id = a.id
                   AND s.provider = ?
                   AND s.model = ?
                WHERE s.id IS NULL
                ORDER BY a.published_at DESC, a.collected_at DESC
                """,
                (provider, model),
            ).fetchall()
        return self._rows_to_articles(rows)

    def get_scored_article_ids_for(self, provider: str, model: str) -> set[int]:
        if not provider or not model:
            raise ValueError("provider and model are required for provider-aware scoring")
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT article_id FROM scores WHERE provider = ? AND model = ?",
                (provider, model),
            ).fetchall()
        return {int(row["article_id"]) for row in rows}

    def _rows_to_articles(self, rows: list[sqlite3.Row]) -> list[tuple[Article, int]]:
        result: list[tuple[Article, int]] = []
        for row in rows:
            article = Article(
                source=row["source"],
                title=row["title"],
                url=row["url"],
                published_at=_parse_dt(row["published_at"]),
                summary=row["summary"] or "",
                content_hash=row["content_hash"],
                raw_excerpt=row["raw_excerpt"] or "",
            )
            result.append((article, int(row["id"])))
        return result

    def save_score(self, score: ScoreResult) -> None:
        if not score.provider or not score.model:
            raise ValueError("score.provider and score.model are required")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO scores
                    (article_id, provider, model, relevance_score, fx_channel,
                     likely_usdjpy_direction, confidence, summary,
                     why_it_matters, source_citation, model_raw, scored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id, provider, model) DO UPDATE SET
                    relevance_score = excluded.relevance_score,
                    fx_channel = excluded.fx_channel,
                    likely_usdjpy_direction = excluded.likely_usdjpy_direction,
                    confidence = excluded.confidence,
                    summary = excluded.summary,
                    why_it_matters = excluded.why_it_matters,
                    source_citation = excluded.source_citation,
                    model_raw = excluded.model_raw,
                    scored_at = excluded.scored_at
                """,
                (
                    score.article_id,
                    score.provider,
                    score.model,
                    score.relevance_score,
                    score.fx_channel,
                    score.likely_usdjpy_direction,
                    score.confidence,
                    score.summary,
                    score.why_it_matters,
                    score.source_citation,
                    score.model_raw,
                    _utc_now_iso(),
                ),
            )

    def get_top_scored(
        self,
        min_relevance: int,
        limit: int = 15,
        recency_hours: int | None = None,
        *,
        provider: str,
        model: str,
    ) -> list[dict[str, Any]]:
        if not provider or not model:
            raise ValueError("provider and model are required for summary reads")
        # Effective timestamp = published_at, falling back to collected_at for
        # undated items. Ordering and the recency window both use it so the
        # summary surfaces *recent* high-scored news, not the all-time top score.
        ts = "COALESCE(a.published_at, a.collected_at)"
        where = ["s.provider = ?", "s.model = ?", "s.relevance_score >= ?"]
        params: list[Any] = [provider, model, min_relevance]
        if recency_hours is not None:
            where.append(f"{ts} >= ?")
            params.append(_cutoff_iso(recency_hours))
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.collected_at,
                       s.provider, s.model, s.relevance_score, s.fx_channel,
                       s.likely_usdjpy_direction,
                       s.confidence, s.summary, s.why_it_matters, s.source_citation
                FROM scores s
                JOIN articles a ON a.id = s.article_id
                WHERE {" AND ".join(where)}
                ORDER BY s.relevance_score DESC, {ts} DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recently_scored_all(
        self,
        limit: int = 50,
        recency_hours: int | None = None,
        *,
        provider: str,
        model: str,
    ) -> list[dict[str, Any]]:
        if not provider or not model:
            raise ValueError("provider and model are required for summary reads")
        ts = "COALESCE(a.published_at, a.collected_at)"
        where = ["s.provider = ?", "s.model = ?"]
        params: list[Any] = [provider, model]
        if recency_hours is not None:
            where.append(f"{ts} >= ?")
            params.append(_cutoff_iso(recency_hours))
        params.append(limit)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.collected_at,
                       s.provider, s.model, s.relevance_score, s.fx_channel,
                       s.likely_usdjpy_direction,
                       s.confidence, s.summary, s.why_it_matters, s.source_citation
                FROM scores s
                JOIN articles a ON a.id = s.article_id
                {where_sql}
                ORDER BY s.relevance_score DESC, {ts} DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def save_summary_run(
        self,
        file_path: str,
        body: str,
        article_count: int,
        top_score: int,
        *,
        provider: str,
        model: str,
    ) -> int:
        if not provider or not model:
            raise ValueError("provider and model are required for summary runs")
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO summary_runs
                    (generated_at, file_path, provider, model, article_count,
                     top_score, body)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    file_path,
                    provider,
                    model,
                    article_count,
                    top_score,
                    body,
                ),
            )
            return int(cur.lastrowid)

    def create_run_history(
        self,
        *,
        run_id: str,
        trigger_type: str,
        llm_model: str,
    ) -> int:
        """Insert a scheduled/manual run record at start; returns row id."""
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO run_history
                    (run_id, started_at, status, trigger_type, llm_model)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, _utc_now_iso(), "running", trigger_type, llm_model),
            )
            return int(cur.lastrowid)

    def finish_run_history(
        self,
        history_id: int,
        *,
        status: str,
        markdown_path: str | None = None,
        docx_path: str | None = None,
        email_sent: bool = False,
        email_recipients: str | None = None,
        error_message: str | None = None,
        source_count: int | None = None,
        story_count: int | None = None,
    ) -> None:
        """Update run_history when a workflow completes or fails."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE run_history
                SET finished_at = ?,
                    status = ?,
                    markdown_path = ?,
                    docx_path = ?,
                    email_sent = ?,
                    email_recipients = ?,
                    error_message = ?,
                    source_count = ?,
                    story_count = ?
                WHERE id = ?
                """,
                (
                    _utc_now_iso(),
                    status,
                    markdown_path,
                    docx_path,
                    1 if email_sent else 0,
                    email_recipients,
                    error_message,
                    source_count,
                    story_count,
                    history_id,
                ),
            )

    def stats(self) -> dict[str, int]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
            unscored = conn.execute(
                "SELECT COUNT(*) AS c FROM articles WHERE scored = 0"
            ).fetchone()["c"]
            scored = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()["c"]
        return {"articles": total, "unscored": unscored, "scored": scored}


def get_store(settings: Settings) -> Store:
    return Store(
        settings.db_path,
        legacy_provider="deepseek",
        legacy_model=settings.deepseek_model,
    )
