from datetime import datetime, timezone
from pathlib import Path

from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article, ScoreResult
from finance_news_tracker.store import Store


def test_upsert_dedupes(tmp_path: Path):
    db = tmp_path / "test.db"
    store = Store(db)
    article = Article(
        source="boj_whatsnew",
        title="Test Release",
        url="https://example.com/a",
        published_at=datetime.now(timezone.utc),
        content_hash="abc123",
    )
    id1, new1 = store.upsert_article(article)
    id2, new2 = store.upsert_article(article)
    assert new1 is True
    assert new2 is False
    assert id1 == id2
    assert store.stats()["articles"] == 1


def test_save_score_marks_scored(tmp_path: Path):
    db = tmp_path / "test.db"
    store = Store(db)
    article = Article(
        source="nikkei_asia",
        title="Yen moves on Fed outlook",
        url="https://example.com/b",
        content_hash="def456",
    )
    aid, _ = store.upsert_article(article)
    store.save_score(
        ScoreResult(
            article_id=aid,
            relevance_score=75,
            fx_channel="monetary_policy",
            likely_usdjpy_direction="usd_jpy_up",
            confidence="medium",
            summary="Test summary",
            why_it_matters="Rate differential widens",
            source_citation="Test",
        )
    )
    assert store.stats()["scored"] == 1
    assert store.get_unscored_articles() == []
    top = store.get_top_scored(40, limit=5)
    assert len(top) == 1
    assert top[0]["relevance_score"] == 75
