"""Policy & Competitor Tracker persistence and human action fields."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from finance_news_tracker.models import AnalysisResult, Article, ScoreResult
from finance_news_tracker.store import Store
from tests.conftest import make_test_settings


def _seed_article(store: Store) -> tuple[int, dict]:
    article = Article(
        source="anre_news_release",
        title="METI BESS subsidy update",
        url="https://example.com/subsidy",
        published_at=datetime.now(timezone.utc),
        summary="Subsidy window opens",
        content_hash="tracker-1",
    )
    aid, _ = store.upsert_article(article)
    store.save_score(
        ScoreResult(
            article_id=aid,
            relevance_score=85,
            category="policy_market",
            signal="positive",
            confidence="high",
            summary="Subsidy opens",
            why_it_matters="Supports BESS returns",
            source_citation="METI",
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
    settings = make_test_settings(tmp_path, profile_id="jp_storage")
    store = Store(settings.db_path)
    aid, row = _seed_article(store)
    analysis = AnalysisResult(
        article_id=aid,
        profile_id="jp_storage",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
        category="policy",
        entity="METI",
        impact="Improves BESS subsidy stack",
        suggested_action="Brief BD team",
    )
    item_id = store.upsert_tracker_item_from_analysis(article=row, analysis=analysis)
    store.update_tracker_item_action(item_id, owner="alice", status="in_progress")

    # Re-run analysis with updated impact — must not clobber owner/status
    analysis.impact = "Updated impact wording"
    analysis.suggested_action = "Escalate to IC"
    store.upsert_tracker_item_from_analysis(article=row, analysis=analysis)

    items = store.list_tracker_items(
        profile_id="jp_storage",
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
    assert items[0].original_link == "https://example.com/subsidy"


def test_tracker_unique_per_model_combination(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="jp_storage")
    store = Store(settings.db_path)
    aid, row = _seed_article(store)
    a1 = AnalysisResult(
        article_id=aid,
        profile_id="jp_storage",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt-a",
        category="policy",
        entity="METI",
        impact="A",
        suggested_action="Monitor only",
    )
    a2 = AnalysisResult(
        article_id=aid,
        profile_id="jp_storage",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt-b",
        category="policy",
        entity="METI",
        impact="B",
        suggested_action="Monitor only",
    )
    store.upsert_tracker_item_from_analysis(article=row, analysis=a1)
    store.upsert_tracker_item_from_analysis(article=row, analysis=a2)
    all_items = store.list_tracker_items(profile_id="jp_storage", limit=20)
    assert len(all_items) == 2


def test_tracker_profile_isolation(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="jp_storage")
    store = Store(settings.db_path)
    aid, row = _seed_article(store)
    store.upsert_tracker_item_from_analysis(
        article=row,
        analysis=AnalysisResult(
            article_id=aid,
            profile_id="jp_storage",
            scoring_provider="deepseek",
            scoring_model="flash",
            analysis_provider="openai",
            analysis_model="gpt",
            category="policy",
            entity="METI",
            impact="x",
            suggested_action="Monitor only",
        ),
    )
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
            impact="y",
            suggested_action="Monitor only",
        ),
    )
    jp = store.list_tracker_items(profile_id="jp_storage")
    fx = store.list_tracker_items(profile_id="usdjpy")
    assert len(jp) == 1
    assert len(fx) == 1
    assert jp[0].entity == "METI"
    assert fx[0].entity == "BOJ"


def test_analysis_upsert_and_lookup(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="jp_storage")
    store = Store(settings.db_path)
    aid, _row = _seed_article(store)
    analysis = AnalysisResult(
        article_id=aid,
        profile_id="jp_storage",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
        category="policy",
        entity="METI",
        impact="impact",
        suggested_action="action",
    )
    store.save_analysis(analysis)
    found = store.get_analyses_for_articles(
        [aid],
        profile_id="jp_storage",
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
    )
    assert aid in found
    assert found[aid].entity == "METI"
