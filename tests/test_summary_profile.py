"""SummaryProfile contract: base inheritance, section order, fallbacks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from finance_news_tracker.profiles import get_profile
from finance_news_tracker.profiles.summary_base import (
    BASE_SUMMARY_PROFILE,
    build_base_summary_profile,
    derive_summary_profile,
)
from finance_news_tracker.summary import render_markdown
from finance_news_tracker.word_export import write_word_summary
from tests.conftest import make_test_settings


def test_base_summary_profile_has_core_sections():
    ids = [s.id for s in BASE_SUMMARY_PROFILE.sections]
    assert ids == ["executive_summary", "top_stories", "watchlist", "citations"]


def test_usdjpy_uses_market_read_via_base_resolver():
    profile = get_profile("usdjpy")
    summary = profile.resolve_summary_profile()
    assert summary.narrative_field == "market_read"
    assert summary.narrative_label == "Market Read"
    assert "Top Stories" in [s.title for s in summary.sections]


def test_jp_storage_summary_has_bess_sections():
    profile = get_profile("jp_storage")
    summary = profile.resolve_summary_profile()
    ids = [s.id for s in summary.sections]
    assert "policy" in ids
    assert "occto_grid" in ids
    assert "market_rules" in ids
    assert "competitors" in ids
    assert "financing_ma" in ids
    assert summary.narrative_field == "executive_summary"


def test_derive_summary_profile_override():
    derived = derive_summary_profile(
        BASE_SUMMARY_PROFILE,
        id="custom",
        narrative_label="Desk Read",
    )
    assert derived.id == "custom"
    assert derived.narrative_label == "Desk Read"
    assert BASE_SUMMARY_PROFILE.narrative_label == "Executive Summary"


def test_render_markdown_follows_summary_profile_sections(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="jp_storage")
    now = datetime.now(timezone.utc)
    items = [
        {
            "id": 1,
            "source": "anre_news_release",
            "title": "METI capacity market update",
            "url": "https://example.com/policy",
            "published_at": now.isoformat(),
            "relevance_score": 88,
            "category": "policy",
            "analysis_category": "policy",
            "signal": "positive",
            "summary": "Auction rule tweak",
            "why_it_matters": "Affects BESS revenue",
            "impact": "Raises BESS capacity-market upside",
            "suggested_action": "Brief development team",
            "entity": "METI",
        },
        {
            "id": 2,
            "source": "occto_rss",
            "title": "OCCTO grid committee note",
            "url": "https://example.com/grid",
            "published_at": now.isoformat(),
            "relevance_score": 75,
            "category": "occto_grid",
            "analysis_category": "occto_grid",
            "signal": "neutral",
            "summary": "Interconnection discussion",
            "why_it_matters": "Grid access",
            "impact": "May change interconnection queueing",
            "suggested_action": "Monitor only",
            "entity": "OCCTO",
        },
    ]
    body = render_markdown(
        {
            "executive_summary": "BESS policy and grid updates this week.",
            "watchlist": ["Capacity auction timetable"],
        },
        items,
        now,
        settings,
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
        citation_items=items,
    )
    assert "## Executive Summary" in body
    assert "## Key Policy Updates" in body
    assert "## OCCTO / Grid Updates" in body
    assert "Impact on BESS" in body
    assert "Suggested Action" in body
    assert "METI capacity market update" in body
    assert "OCCTO grid committee note" in body
    # No profile-id hardcoding in body beyond metadata
    assert "**Profile:** jp_storage" in body


def test_render_fallback_when_narrative_missing(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="usdjpy")
    now = datetime.now(timezone.utc)
    body = render_markdown(
        {"watchlist": []},
        [],
        now,
        settings,
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="deepseek",
        analysis_model="flash",
    )
    assert "## Market Read" in body
    assert "Automated LLM synthesis unavailable" in body
    assert "## Watchlist" in body


def test_markdown_and_word_share_section_titles(tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="jp_storage")
    now = datetime.now(timezone.utc)
    items = [
        {
            "id": 1,
            "source": "jera_cross_news",
            "title": "JERA storage FID",
            "url": "https://example.com/jera",
            "published_at": now.isoformat(),
            "relevance_score": 92,
            "category": "competitors",
            "analysis_category": "competitors",
            "signal": "positive",
            "summary": "Project FID",
            "why_it_matters": "Competitor move",
            "impact": "Competitive pressure in Kyushu",
            "suggested_action": "Update competitor tracker",
            "entity": "JERA Cross",
        }
    ]
    llm = {
        "executive_summary": "Competitor FID this week.",
        "watchlist": ["Watch JERA COD"],
    }
    md = render_markdown(
        llm,
        items,
        now,
        settings,
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
        citation_items=items,
    )
    docx_path = write_word_summary(
        llm,
        items,
        now,
        tmp_path / "memo.docx",
        settings=settings,
        citation_items=items,
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt",
    )
    assert docx_path.exists()
    for title in (
        "Executive Summary",
        "Competitor Movements",
        "Recommended Follow-ups / Watchlist",
        "Source Citations",
    ):
        assert f"## {title}" in md


def test_build_base_summary_profile_extra_sections():
    from finance_news_tracker.profiles.base import SummarySection

    profile = build_base_summary_profile(
        profile_id="with_extra",
        extra_sections=[
            SummarySection(id="risks", title="Risks", kind="watchlist"),
        ],
    )
    ids = [s.id for s in profile.sections]
    assert ids.index("top_stories") < ids.index("risks") < ids.index("watchlist")
