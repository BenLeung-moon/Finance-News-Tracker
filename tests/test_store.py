import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from finance_news_tracker.models import Article, ScoreResult
from finance_news_tracker.store import Store


def _article(content_hash: str = "abc123") -> Article:
    return Article(
        source="nikkei_asia",
        title="Yen moves on Fed outlook",
        url=f"https://example.com/{content_hash}",
        published_at=datetime.now(timezone.utc),
        summary="Fed outlook moves USD/JPY.",
        content_hash=content_hash,
    )


def _score(
    article_id: int,
    provider: str,
    model: str,
    relevance_score: int,
) -> ScoreResult:
    return ScoreResult(
        article_id=article_id,
        relevance_score=relevance_score,
        category="monetary_policy",
        signal="usd_jpy_up",
        confidence="medium",
        summary=f"{provider} summary",
        why_it_matters="Rate differential widens",
        source_citation="Test",
        provider=provider,
        model=model,
    )


def test_upsert_dedupes(tmp_path: Path):
    db = tmp_path / "test.db"
    store = Store(db)
    article = _article()
    id1, new1 = store.upsert_article(article)
    id2, new2 = store.upsert_article(article)
    assert new1 is True
    assert new2 is False
    assert id1 == id2
    assert store.stats()["articles"] == 1


def test_one_article_can_have_scores_for_three_providers(tmp_path: Path):
    db = tmp_path / "test.db"
    store = Store(db)
    aid, _ = store.upsert_article(_article("def456"))

    store.save_score(_score(aid, "deepseek", "deepseek-v4-flash", 75))
    store.save_score(_score(aid, "openai", "gpt-5.4-mini", 70))
    store.save_score(_score(aid, "anthropic", "claude-haiku-4-5-20251001", 65))

    assert store.stats()["score_rows"] == 3
    assert store.get_unscored_for("deepseek", "deepseek-v4-flash") == []
    assert store.get_unscored_for("openai", "gpt-5.4-mini") == []
    assert store.get_unscored_for("anthropic", "claude-haiku-4-5-20251001") == []


def test_unscored_for_provider_ignores_other_provider_scores(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    aid, _ = store.upsert_article(_article("provider-gap"))
    store.save_score(_score(aid, "deepseek", "deepseek-v4-flash", 75))

    assert store.get_unscored_for("deepseek", "deepseek-v4-flash") == []
    openai_unscored = store.get_unscored_for("openai", "gpt-5.4-mini")
    assert len(openai_unscored) == 1
    assert openai_unscored[0][1] == aid


def test_summary_reads_never_mix_provider_models(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    aid, _ = store.upsert_article(_article("summary-filter"))
    store.save_score(_score(aid, "deepseek", "deepseek-v4-flash", 75))
    store.save_score(_score(aid, "openai", "gpt-5.4-mini", 95))

    top = store.get_top_scored(
        40,
        limit=5,
        provider="deepseek",
        model="deepseek-v4-flash",
    )
    recent = store.get_recently_scored_all(
        limit=5,
        provider="deepseek",
        model="deepseek-v4-flash",
    )

    assert len(top) == 1
    assert top[0]["provider"] == "deepseek"
    assert top[0]["relevance_score"] == 75
    assert len(recent) == 1
    assert recent[0]["provider"] == "deepseek"


def test_save_score_does_not_block_another_provider_with_articles_scored(tmp_path: Path):
    store = Store(tmp_path / "test.db")
    aid, _ = store.upsert_article(_article("legacy-flag"))
    store.save_score(_score(aid, "deepseek", "deepseek-v4-flash", 75))

    with store._conn() as conn:
        scored_flag = conn.execute(
            "SELECT scored FROM articles WHERE id = ?",
            (aid,),
        ).fetchone()["scored"]

    assert scored_flag == 0
    assert store.get_unscored_for("openai", "gpt-5.4-mini")[0][1] == aid


def test_rebuilds_legacy_score_table_with_provider_model(tmp_path: Path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE articles (
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
        CREATE TABLE scores (
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
            scored_at TEXT NOT NULL
        );
        INSERT INTO articles
            (id, source, title, url, content_hash, collected_at, scored)
        VALUES
            (1, 'nikkei_asia', 'Legacy article', 'https://example.com/legacy',
             'legacy', '2026-06-11T00:00:00+00:00', 1);
        INSERT INTO scores
            (article_id, relevance_score, fx_channel, likely_usdjpy_direction,
             confidence, summary, why_it_matters, source_citation, model_raw, scored_at)
        VALUES
            (1, 80, 'monetary_policy', 'usd_jpy_up', 'high', 'Legacy summary',
             'Rates', 'Legacy', '{}', '2026-06-11T00:00:00+00:00');
        """
    )
    conn.close()

    store = Store(db, legacy_model="deepseek-v4-flash")
    rows = store.get_top_scored(
        40,
        provider="deepseek",
        model="deepseek-v4-flash",
    )

    assert len(rows) == 1
    assert rows[0]["provider"] == "deepseek"
    assert rows[0]["category"] == "monetary_policy"
    assert rows[0]["signal"] == "usd_jpy_up"


def test_migrates_legacy_fx_columns_to_category_signal(tmp_path: Path):
    db = tmp_path / "legacy_cols.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE articles (
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
        CREATE TABLE scores (
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
            UNIQUE(article_id, provider, model)
        );
        INSERT INTO articles
            (id, source, title, url, content_hash, collected_at, scored)
        VALUES
            (1, 'nikkei_asia', 'Column migration', 'https://example.com/migrate',
             'migrate', '2026-06-11T00:00:00+00:00', 1);
        INSERT INTO scores
            (article_id, provider, model, relevance_score, fx_channel,
             likely_usdjpy_direction, confidence, summary, why_it_matters,
             source_citation, model_raw, scored_at)
        VALUES
            (1, 'deepseek', 'deepseek-v4-flash', 88, 'intervention',
             'usd_jpy_down', 'high', 'Intervention risk', 'MOF rhetoric',
             'Legacy', '{}', '2026-06-11T00:00:00+00:00');
        """
    )
    conn.close()

    store = Store(db)
    rows = store.get_top_scored(40, provider="deepseek", model="deepseek-v4-flash")
    assert len(rows) == 1
    assert rows[0]["category"] == "intervention"
    assert rows[0]["signal"] == "usd_jpy_down"


def test_legacy_scores_migration_requires_backup_for_tracker_db(tmp_path: Path):
    db = tmp_path / "tracker.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE articles (
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
        CREATE TABLE scores (
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
            scored_at TEXT NOT NULL
        );
        INSERT INTO articles
            (id, source, title, url, content_hash, collected_at, scored)
        VALUES
            (1, 'nikkei_asia', 'Needs backup', 'https://example.com/backup',
             'backup', '2026-06-11T00:00:00+00:00', 1);
        INSERT INTO scores
            (article_id, relevance_score, fx_channel, likely_usdjpy_direction,
             confidence, summary, why_it_matters, source_citation, model_raw, scored_at)
        VALUES
            (1, 80, 'monetary_policy', 'usd_jpy_up', 'high', 'Legacy summary',
             'Rates', 'Legacy', '{}', '2026-06-11T00:00:00+00:00');
        """
    )
    conn.close()

    with pytest.raises(RuntimeError, match="backup"):
        Store(db, legacy_model="deepseek-v4-flash")
