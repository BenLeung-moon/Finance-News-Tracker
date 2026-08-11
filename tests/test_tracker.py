"""Policy & Competitor Tracker persistence and human action fields."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from finance_news_tracker.models import AnalysisResult, Article, ScoreResult
from finance_news_tracker.store import Store
from tests.conftest import make_test_settings


def _seed_article(store: Store) -> tuple[int, dict]:
    article = Article(
        source="boj_whatsnew",
        title="BOJ policy statement",
        url="https://example.com/boj-policy",
        published_at=datetime.now(timezone.utc),
        summary="Policy unchanged",
        content_hash="tracker-1",
    )
    aid, _ = store.upsert_article(article)
    store.save_score(
        ScoreResult(
            article_id=aid,
            relevance_score=85,
            category="monetary_policy",
            signal="positive",
            confidence="high",
            summary="Policy unchanged",
            why_it_matters="Supports USD/JPY path",
            source_citation="BOJ",
            provider="deepseek",
            model="flash",
        )
    )
    row = {
        "id": aid,
        "source": article.source,
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "summary": article.summary,
        "relevance_score": 85,
    }
    return aid, row


def test_tracker_upsert_preserves_owner_status(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="usdjpy")
    store = Store(settings.db_path)
    aid, row = _seed_article(store)
    analysis = AnalysisResult(
        article_id=aid,
        profile_id="usdjpy",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
        category="monetary_policy",
        entity="BOJ",
        impact="Keeps USD/JPY sensitive to guidance",
        suggested_action="Brief FX desk",
    )
    item_id = store.upsert_tracker_item_from_analysis(article=row, analysis=analysis)
    store.update_tracker_item_action(item_id, owner="alice", status="in_progress")

    # Re-run analysis with updated impact — must not clobber owner/status
    analysis.impact = "Updated impact wording"
    analysis.suggested_action = "Escalate to IC"
    store.upsert_tracker_item_from_analysis(article=row, analysis=analysis)

    items = store.list_tracker_items(
        profile_id="usdjpy",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
    )
    assert len(items) == 1
    assert items[0].owner == "alice"
    assert items[0].status == "in_progress"
    assert items[0].impact == "Updated impact wording"
    assert items[0].suggested_action == "Escalate to IC"
    assert items[0].original_link == "https://example.com/boj-policy"


def test_tracker_unique_per_model_combination(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="usdjpy")
    store = Store(settings.db_path)
    aid, row = _seed_article(store)
    a1 = AnalysisResult(
        article_id=aid,
        profile_id="usdjpy",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt-a",
        category="monetary_policy",
        entity="BOJ",
        impact="A",
        suggested_action="Monitor only",
    )
    a2 = AnalysisResult(
        article_id=aid,
        profile_id="usdjpy",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt-b",
        category="monetary_policy",
        entity="BOJ",
        impact="B",
        suggested_action="Monitor only",
    )
    store.upsert_tracker_item_from_analysis(article=row, analysis=a1)
    store.upsert_tracker_item_from_analysis(article=row, analysis=a2)
    all_items = store.list_tracker_items(profile_id="usdjpy", limit=20)
    assert len(all_items) == 2


def test_tracker_profile_isolation(tmp_path: Path):
    """Store isolates rows by profile_id string even if only one profile is registered."""
    settings = make_test_settings(tmp_path, profile_id="usdjpy")
    store = Store(settings.db_path)
    aid, row = _seed_article(store)
    store.upsert_tracker_item_from_analysis(
        article=row,
        analysis=AnalysisResult(
            article_id=aid,
            profile_id="usdjpy",
            scoring_provider="deepseek",
            scoring_model="flash",
            analysis_provider="openai",
            analysis_model="gpt",
            category="monetary_policy",
            entity="BOJ",
            impact="x",
            suggested_action="Monitor only",
        ),
    )
    store.upsert_tracker_item_from_analysis(
        article=row,
        analysis=AnalysisResult(
            article_id=aid,
            profile_id="other_theme",
            scoring_provider="deepseek",
            scoring_model="flash",
            analysis_provider="openai",
            analysis_model="gpt",
            category="policy",
            entity="METI",
            impact="y",
            suggested_action="Monitor only",
        ),
    )
    fx = store.list_tracker_items(profile_id="usdjpy")
    other = store.list_tracker_items(profile_id="other_theme")
    assert len(fx) == 1
    assert len(other) == 1
    assert fx[0].entity == "BOJ"
    assert other[0].entity == "METI"


def test_analysis_upsert_and_lookup(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="usdjpy")
    store = Store(settings.db_path)
    aid, _row = _seed_article(store)
    analysis = AnalysisResult(
        article_id=aid,
        profile_id="usdjpy",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
        category="monetary_policy",
        entity="BOJ",
        impact="impact",
        suggested_action="action",
    )
    store.save_analysis(analysis)
    found = store.get_analyses_for_articles(
        [aid],
        profile_id="usdjpy",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
    )
    assert aid in found
    assert found[aid].entity == "BOJ"
