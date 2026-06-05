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
    def __init__(self, db_path: Path):
        self.db_path = db_path
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
                    article_id INTEGER NOT NULL UNIQUE,
                    relevance_score INTEGER NOT NULL,
                    fx_channel TEXT,
                    likely_usdjpy_direction TEXT,
                    confidence TEXT,
                    summary TEXT,
                    why_it_matters TEXT,
                    source_citation TEXT,
                    model_raw TEXT,
                    scored_at TEXT NOT NULL,
                    FOREIGN KEY (article_id) REFERENCES articles(id)
                );

                CREATE TABLE IF NOT EXISTS summary_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    file_path TEXT NOT NULL,
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

    def save_score(self, score: ScoreResult) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scores
                    (article_id, relevance_score, fx_channel,
                     likely_usdjpy_direction, confidence, summary,
                     why_it_matters, source_citation, model_raw, scored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score.article_id,
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
            conn.execute(
                "UPDATE articles SET scored = 1 WHERE id = ?",
                (score.article_id,),
            )

    def get_top_scored(
        self,
        min_relevance: int,
        limit: int = 15,
        recency_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        # Effective timestamp = published_at, falling back to collected_at for
        # undated items. Ordering and the recency window both use it so the
        # summary surfaces *recent* high-scored news, not the all-time top score.
        ts = "COALESCE(a.published_at, a.collected_at)"
        where = ["s.relevance_score >= ?"]
        params: list[Any] = [min_relevance]
        if recency_hours is not None:
            where.append(f"{ts} >= ?")
            params.append(_cutoff_iso(recency_hours))
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.collected_at,
                       s.relevance_score, s.fx_channel, s.likely_usdjpy_direction,
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
    ) -> list[dict[str, Any]]:
        ts = "COALESCE(a.published_at, a.collected_at)"
        where = []
        params: list[Any] = []
        if recency_hours is not None:
            where.append(f"{ts} >= ?")
            params.append(_cutoff_iso(recency_hours))
        params.append(limit)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT a.id, a.source, a.title, a.url, a.published_at, a.collected_at,
                       s.relevance_score, s.fx_channel, s.likely_usdjpy_direction,
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
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO summary_runs
                    (generated_at, file_path, article_count, top_score, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_utc_now_iso(), file_path, article_count, top_score, body),
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
    return Store(settings.db_path)
