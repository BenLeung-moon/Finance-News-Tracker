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
    settings = make_test_settings(tmp_path, profile_id="usdjpy")
    now = datetime.now(timezone.utc)
    items = [
        {
            "id": 1,
            "source": "boj_whatsnew",
            "title": "BOJ holds policy rate",
            "url": "https://example.com/boj",
            "published_at": now.isoformat(),
            "relevance_score": 88,
            "category": "monetary_policy",
            "analysis_category": "monetary_policy",
            "signal": "positive",
            "summary": "Policy unchanged",
            "why_it_matters": "Supports yen path",
            "impact": "USD/JPY remains sensitive to BOJ guidance",
            "suggested_action": "Brief FX desk",
            "entity": "BOJ",
        },
        {
            "id": 2,
            "source": "fed_press_monetary",
            "title": "Fed signals higher for longer",
            "url": "https://example.com/fed",
            "published_at": now.isoformat(),
            "relevance_score": 75,
            "category": "monetary_policy",
            "analysis_category": "monetary_policy",
            "signal": "neutral",
            "summary": "Rates path",
            "why_it_matters": "Rate differential",
            "impact": "Keeps USD bid vs JPY",
            "suggested_action": "Monitor only",
            "entity": "Fed",
        },
    ]
    body = render_markdown(
        {
            "market_read": "BOJ and Fed keep the USD/JPY rate differential in focus.",
            "watchlist": ["BOJ communication calendar"],
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
    assert "## Market Read" in body
    assert "## Top Stories" in body
    assert "BOJ holds policy rate" in body
    assert "Fed signals higher for longer" in body
    assert "**Profile:** usdjpy" in body


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
    settings = make_test_settings(tmp_path, profile_id="usdjpy")
    now = datetime.now(timezone.utc)
    items = [
        {
            "id": 1,
            "source": "nikkei_asia",
            "title": "Yen weakens after soft Tokyo CPI",
            "url": "https://example.com/yen",
            "published_at": now.isoformat(),
            "relevance_score": 92,
            "category": "macro",
            "analysis_category": "macro",
            "signal": "negative",
            "summary": "CPI soft",
            "why_it_matters": "BOJ hike odds",
            "impact": "USD/JPY upside risk remains",
            "suggested_action": "Update FX watchlist",
            "entity": "Japan CPI",
        }
    ]
    llm = {
        "market_read": "Soft CPI keeps yen under pressure.",
        "watchlist": ["Watch next BOJ speakers"],
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
        "Market Read",
        "Top Stories",
        "Watchlist",
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
