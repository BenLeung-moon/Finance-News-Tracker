from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from finance_news_tracker.config import Settings
from finance_news_tracker.models import AnalysisResult, Article, ScoreResult, TrackerItem


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
                    category TEXT,
                    signal TEXT,
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
                    scoring_provider TEXT,
                    scoring_model TEXT,
                    analysis_provider TEXT,
                    analysis_model TEXT,
                    article_count INTEGER,
                    top_score INTEGER,
                    body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    profile_id TEXT NOT NULL,
                    scoring_provider TEXT NOT NULL,
                    scoring_model TEXT NOT NULL,
                    analysis_provider TEXT NOT NULL,
                    analysis_model TEXT NOT NULL,
                    category TEXT,
                    entity TEXT,
                    impact TEXT,
                    suggested_action TEXT,
                    model_raw TEXT,
                    analyzed_at TEXT NOT NULL,
                    FOREIGN KEY (article_id) REFERENCES articles(id),
                    UNIQUE(
                        article_id, profile_id,
                        scoring_provider, scoring_model,
                        analysis_provider, analysis_model
                    )
                );

                CREATE TABLE IF NOT EXISTS tracker_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    profile_id TEXT NOT NULL,
                    scoring_provider TEXT NOT NULL,
                    scoring_model TEXT NOT NULL,
                    analysis_provider TEXT NOT NULL,
                    analysis_model TEXT NOT NULL,
                    item_date TEXT,
                    source TEXT NOT NULL,
                    category TEXT,
                    title TEXT NOT NULL,
                    summary TEXT,
                    relevance_score INTEGER,
                    entity TEXT,
                    impact TEXT,
                    suggested_action TEXT,
                    owner TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    original_link TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (article_id) REFERENCES articles(id),
                    UNIQUE(
                        article_id, profile_id,
                        scoring_provider, scoring_model,
                        analysis_provider, analysis_model
                    )
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
            self._migrate_score_columns_if_needed(conn)
            self._migrate_summary_runs_if_needed(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scores_provider_model_relevance
                    ON scores(provider, model, relevance_score DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_analyses_profile_models
                    ON analyses(
                        profile_id, scoring_provider, scoring_model,
                        analysis_provider, analysis_model
                    )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tracker_items_profile_status
                    ON tracker_items(profile_id, status, updated_at DESC)
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
                category TEXT,
                signal TEXT,
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
                (id, article_id, provider, model, relevance_score, category,
                 signal, confidence, summary, why_it_matters,
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

    def _migrate_score_columns_if_needed(self, conn: sqlite3.Connection) -> None:
        """Rename fx_channel / likely_usdjpy_direction to neutral category / signal."""
        columns = self._table_columns(conn, "scores")
        if "category" in columns and "fx_channel" not in columns:
            return
        if "fx_channel" not in columns:
            return

        existing_count = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()["c"]
        if existing_count and not self._has_real_db_backup():
            raise RuntimeError(
                "scores column migration requires a data/tracker.db backup first. "
                "Create a backup next to the DB before reopening the tracker."
            )

        conn.executescript(
            """
            CREATE TABLE scores_columns_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                relevance_score INTEGER NOT NULL,
                category TEXT,
                signal TEXT,
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
        if "category" in columns:
            conn.execute(
                """
                INSERT INTO scores_columns_new
                    (id, article_id, provider, model, relevance_score, category,
                     signal, confidence, summary, why_it_matters,
                     source_citation, model_raw, scored_at)
                SELECT id, article_id, provider, model, relevance_score,
                       COALESCE(category, fx_channel),
                       COALESCE(signal, likely_usdjpy_direction),
                       confidence, summary, why_it_matters,
                       source_citation, model_raw, scored_at
                FROM scores
                """
            )
        else:
            conn.execute(
                """
                INSERT INTO scores_columns_new
                    (id, article_id, provider, model, relevance_score, category,
                     signal, confidence, summary, why_it_matters,
                     source_citation, model_raw, scored_at)
                SELECT id, article_id, provider, model, relevance_score,
                       fx_channel, likely_usdjpy_direction,
                       confidence, summary, why_it_matters,
                       source_citation, model_raw, scored_at
                FROM scores
                """
            )
        conn.executescript(
            """
            DROP TABLE scores;
            ALTER TABLE scores_columns_new RENAME TO scores;
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
        # Role lineage columns (nullable for older rows)
        for col in (
            "scoring_provider",
            "scoring_model",
            "analysis_provider",
            "analysis_model",
        ):
            if col not in columns:
                conn.execute(f"ALTER TABLE summary_runs ADD COLUMN {col} TEXT")

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

    def get_unscored_for(
        self,
        provider: str,
        model: str,
        *,
        source_ids: set[str] | None = None,
    ) -> list[tuple[Article, int]]:
        if not provider or not model:
            raise ValueError("provider and model are required for provider-aware scoring")
        if source_ids is not None and not source_ids:
            return []
        source_sql = ""
        params: list[Any] = [provider, model]
        if source_ids is not None:
            placeholders = ", ".join("?" for _ in source_ids)
            source_sql = f" AND a.source IN ({placeholders})"
            params.extend(sorted(source_ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.summary,
                       a.content_hash, a.raw_excerpt
                FROM articles a
                LEFT JOIN scores s
                    ON s.article_id = a.id
                   AND s.provider = ?
                   AND s.model = ?
                WHERE s.id IS NULL
                {source_sql}
                ORDER BY a.published_at DESC, a.collected_at DESC
                """,
                params,
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
                    (article_id, provider, model, relevance_score, category,
                     signal, confidence, summary,
                     why_it_matters, source_citation, model_raw, scored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(article_id, provider, model) DO UPDATE SET
                    relevance_score = excluded.relevance_score,
                    category = excluded.category,
                    signal = excluded.signal,
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
                    score.category,
                    score.signal,
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
        source_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not provider or not model:
            raise ValueError("provider and model are required for summary reads")
        if source_ids is not None and not source_ids:
            return []
        # Effective timestamp = published_at, falling back to collected_at for
        # undated items. Ordering and the recency window both use it so the
        # summary surfaces *recent* high-scored news, not the all-time top score.
        ts = "COALESCE(a.published_at, a.collected_at)"
        where = ["s.provider = ?", "s.model = ?", "s.relevance_score >= ?"]
        params: list[Any] = [provider, model, min_relevance]
        if source_ids is not None:
            placeholders = ", ".join("?" for _ in source_ids)
            where.append(f"a.source IN ({placeholders})")
            params.extend(sorted(source_ids))
        if recency_hours is not None:
            where.append(f"{ts} >= ?")
            params.append(_cutoff_iso(recency_hours))
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.collected_at,
                       s.provider, s.model, s.relevance_score, s.category,
                       s.signal,
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
        source_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not provider or not model:
            raise ValueError("provider and model are required for summary reads")
        if source_ids is not None and not source_ids:
            return []
        ts = "COALESCE(a.published_at, a.collected_at)"
        where = ["s.provider = ?", "s.model = ?"]
        params: list[Any] = [provider, model]
        if source_ids is not None:
            placeholders = ", ".join("?" for _ in source_ids)
            where.append(f"a.source IN ({placeholders})")
            params.extend(sorted(source_ids))
        if recency_hours is not None:
            where.append(f"{ts} >= ?")
            params.append(_cutoff_iso(recency_hours))
        params.append(limit)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.collected_at,
                       s.provider, s.model, s.relevance_score, s.category,
                       s.signal,
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

    def save_analysis(self, analysis: AnalysisResult) -> None:
        """Upsert analysis for an article + scoring/analysis model combination."""
        if not analysis.scoring_provider or not analysis.scoring_model:
            raise ValueError("scoring_provider and scoring_model are required")
        if not analysis.analysis_provider or not analysis.analysis_model:
            raise ValueError("analysis_provider and analysis_model are required")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO analyses
                    (article_id, profile_id, scoring_provider, scoring_model,
                     analysis_provider, analysis_model, category, entity,
                     impact, suggested_action, model_raw, analyzed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    article_id, profile_id,
                    scoring_provider, scoring_model,
                    analysis_provider, analysis_model
                ) DO UPDATE SET
                    category = excluded.category,
                    entity = excluded.entity,
                    impact = excluded.impact,
                    suggested_action = excluded.suggested_action,
                    model_raw = excluded.model_raw,
                    analyzed_at = excluded.analyzed_at
                """,
                (
                    analysis.article_id,
                    analysis.profile_id,
                    analysis.scoring_provider,
                    analysis.scoring_model,
                    analysis.analysis_provider,
                    analysis.analysis_model,
                    analysis.category,
                    analysis.entity,
                    analysis.impact,
                    analysis.suggested_action,
                    analysis.model_raw,
                    _utc_now_iso(),
                ),
            )

    def get_analyses_for_articles(
        self,
        article_ids: list[int],
        *,
        profile_id: str,
        scoring_provider: str,
        scoring_model: str,
        analysis_provider: str,
        analysis_model: str,
    ) -> dict[int, AnalysisResult]:
        if not article_ids:
            return {}
        placeholders = ", ".join("?" for _ in article_ids)
        params: list[Any] = [
            profile_id,
            scoring_provider,
            scoring_model,
            analysis_provider,
            analysis_model,
            *article_ids,
        ]
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT article_id, profile_id, scoring_provider, scoring_model,
                       analysis_provider, analysis_model, category, entity,
                       impact, suggested_action, model_raw
                FROM analyses
                WHERE profile_id = ?
                  AND scoring_provider = ?
                  AND scoring_model = ?
                  AND analysis_provider = ?
                  AND analysis_model = ?
                  AND article_id IN ({placeholders})
                """,
                params,
            ).fetchall()
        return {
            int(row["article_id"]): AnalysisResult(
                article_id=int(row["article_id"]),
                profile_id=row["profile_id"],
                scoring_provider=row["scoring_provider"],
                scoring_model=row["scoring_model"],
                analysis_provider=row["analysis_provider"],
                analysis_model=row["analysis_model"],
                category=row["category"] or "other",
                entity=row["entity"] or "n/a",
                impact=row["impact"] or "",
                suggested_action=row["suggested_action"] or "Monitor only",
                model_raw=row["model_raw"] or "",
            )
            for row in rows
        }

    def upsert_tracker_item_from_analysis(
        self,
        *,
        article: dict[str, Any],
        analysis: AnalysisResult,
    ) -> int:
        """Create/update Tracker row from analysis without overwriting Owner/Status.

        中文注解：重复运行只刷新分析字段；人工 Owner/Status 保持不变。
        """
        now = _utc_now_iso()
        item_date = article.get("published_at") or article.get("collected_at")
        if isinstance(item_date, str):
            item_date_value = item_date
        else:
            item_date_value = None
        with self._conn() as conn:
            existing = conn.execute(
                """
                SELECT id, owner, status FROM tracker_items
                WHERE article_id = ?
                  AND profile_id = ?
                  AND scoring_provider = ?
                  AND scoring_model = ?
                  AND analysis_provider = ?
                  AND analysis_model = ?
                """,
                (
                    analysis.article_id,
                    analysis.profile_id,
                    analysis.scoring_provider,
                    analysis.scoring_model,
                    analysis.analysis_provider,
                    analysis.analysis_model,
                ),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE tracker_items
                    SET item_date = ?,
                        source = ?,
                        category = ?,
                        title = ?,
                        summary = ?,
                        relevance_score = ?,
                        entity = ?,
                        impact = ?,
                        suggested_action = ?,
                        original_link = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        item_date_value,
                        str(article.get("source") or ""),
                        analysis.category,
                        str(article.get("title") or ""),
                        str(article.get("summary") or ""),
                        int(article.get("relevance_score") or 0),
                        analysis.entity,
                        analysis.impact,
                        analysis.suggested_action,
                        str(article.get("url") or ""),
                        now,
                        int(existing["id"]),
                    ),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO tracker_items
                    (article_id, profile_id, scoring_provider, scoring_model,
                     analysis_provider, analysis_model, item_date, source,
                     category, title, summary, relevance_score, entity, impact,
                     suggested_action, owner, status, original_link,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending',
                        ?, ?, ?)
                """,
                (
                    analysis.article_id,
                    analysis.profile_id,
                    analysis.scoring_provider,
                    analysis.scoring_model,
                    analysis.analysis_provider,
                    analysis.analysis_model,
                    item_date_value,
                    str(article.get("source") or ""),
                    analysis.category,
                    str(article.get("title") or ""),
                    str(article.get("summary") or ""),
                    int(article.get("relevance_score") or 0),
                    analysis.entity,
                    analysis.impact,
                    analysis.suggested_action,
                    str(article.get("url") or ""),
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def update_tracker_item_action(
        self,
        tracker_item_id: int,
        *,
        owner: str | None = None,
        status: str | None = None,
    ) -> None:
        """Human-only update for Owner / Status action fields."""
        sets: list[str] = ["updated_at = ?"]
        params: list[Any] = [_utc_now_iso()]
        if owner is not None:
            sets.append("owner = ?")
            params.append(owner)
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if len(params) == 1:
            raise ValueError("owner and/or status must be provided")
        params.append(tracker_item_id)
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE tracker_items SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            if cur.rowcount == 0:
                raise ValueError(f"tracker_item id={tracker_item_id} not found")

    def list_tracker_items(
        self,
        *,
        profile_id: str,
        scoring_provider: str | None = None,
        scoring_model: str | None = None,
        analysis_provider: str | None = None,
        analysis_model: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[TrackerItem]:
        where = ["profile_id = ?"]
        params: list[Any] = [profile_id]
        if scoring_provider:
            where.append("scoring_provider = ?")
            params.append(scoring_provider)
        if scoring_model:
            where.append("scoring_model = ?")
            params.append(scoring_model)
        if analysis_provider:
            where.append("analysis_provider = ?")
            params.append(analysis_provider)
        if analysis_model:
            where.append("analysis_model = ?")
            params.append(analysis_model)
        if status:
            where.append("status = ?")
            params.append(status)
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT id, article_id, profile_id, scoring_provider, scoring_model,
                       analysis_provider, analysis_model, item_date, source,
                       category, title, summary, relevance_score, entity, impact,
                       suggested_action, owner, status, original_link
                FROM tracker_items
                WHERE {" AND ".join(where)}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            TrackerItem(
                id=int(row["id"]),
                article_id=int(row["article_id"]),
                profile_id=row["profile_id"],
                scoring_provider=row["scoring_provider"],
                scoring_model=row["scoring_model"],
                analysis_provider=row["analysis_provider"],
                analysis_model=row["analysis_model"],
                item_date=row["item_date"],
                source=row["source"],
                category=row["category"] or "other",
                title=row["title"],
                summary=row["summary"] or "",
                relevance_score=int(row["relevance_score"] or 0),
                entity=row["entity"] or "n/a",
                impact=row["impact"] or "",
                suggested_action=row["suggested_action"] or "Monitor only",
                owner=row["owner"],
                status=row["status"] or "pending",
                original_link=row["original_link"],
            )
            for row in rows
        ]

    def save_summary_run(
        self,
        file_path: str,
        body: str,
        article_count: int,
        top_score: int,
        *,
        provider: str,
        model: str,
        scoring_provider: str | None = None,
        scoring_model: str | None = None,
        analysis_provider: str | None = None,
        analysis_model: str | None = None,
    ) -> int:
        if not provider or not model:
            raise ValueError("provider and model are required for summary runs")
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO summary_runs
                    (generated_at, file_path, provider, model,
                     scoring_provider, scoring_model,
                     analysis_provider, analysis_model,
                     article_count, top_score, body)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now_iso(),
                    file_path,
                    provider,
                    model,
                    scoring_provider or provider,
                    scoring_model or model,
                    analysis_provider or provider,
                    analysis_model or model,
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
        """Return article totals and provider/model score row counts.

        中文注解：`articles.scored` 是遗留字段，不再反映 provider-aware 评分状态。
        """
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
            score_rows = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()["c"]
        return {"articles": total, "score_rows": score_rows}


def get_store(settings: Settings) -> Store:
    return Store(
        settings.db_path,
        legacy_provider="deepseek",
        legacy_model=settings.deepseek_model,
    )
