"""Japan BESS end-to-end: scored articles → analysis → tracker → memo."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from finance_news_tracker.models import AnalysisResult, Article, ScoreResult
from finance_news_tracker.store import Store
from finance_news_tracker.summary import write_executive_summary
from tests.conftest import make_test_settings


def test_jp_storage_score_analysis_memo_tracker(monkeypatch, tmp_path: Path):
    settings = make_test_settings(tmp_path, profile_id="jp_storage")
    store = Store(settings.db_path)

    articles = [
        (
            "policy-1",
            "anre_news_release",
            "METI announces capacity market reform",
            "policy_market",
            "policy",
        ),
        (
            "grid-1",
            "occto_rss",
            "OCCTO publishes interconnection update",
            "policy_market",
            "occto_grid",
        ),
        (
            "corp-1",
            "sumitomo_release",
            "Sumitomo invests in BESS platform",
            "corporate_activity",
            "competitors",
        ),
        (
            "fin-1",
            "itochu_press",
            "Itochu closes storage financing",
            "financing",
            "financing_ma",
        ),
    ]
    for content_hash, source, title, score_cat, _analysis_cat in articles:
        aid, _ = store.upsert_article(
            Article(
                source=source,
                title=title,
                url=f"https://example.com/{content_hash}",
                published_at=datetime.now(timezone.utc),
                summary=title,
                content_hash=content_hash,
            )
        )
        store.save_score(
            ScoreResult(
                article_id=aid,
                relevance_score=80,
                category=score_cat,
                signal="positive",
                confidence="high",
                summary=title,
                why_it_matters="Relevant to Japan BESS",
                source_citation=title,
                provider="deepseek",
                model="deepseek-v4-flash",
            )
        )

    def fake_analyze(items, settings, **kwargs):
        mapping = {a[2]: a[4] for a in articles}
        return [
            AnalysisResult(
                article_id=int(item["id"]),
                profile_id="jp_storage",
                scoring_provider=kwargs["scoring_provider"],
                scoring_model=kwargs["scoring_model"],
                analysis_provider=kwargs.get("analysis_provider") or "openai",
                analysis_model=kwargs.get("analysis_model") or "gpt-5.4-mini",
                category=mapping[item["title"]],
                entity=item["title"].split()[0],
                impact=f"Impact for {item['title']}",
                suggested_action="Brief Japan BD",
            )
            for item in items
        ]

    monkeypatch.setattr(
        "finance_news_tracker.summary.analyze_items_batch",
        fake_analyze,
    )
    monkeypatch.setattr(
        "finance_news_tracker.summary.generate_executive_summary_llm",
        lambda *args, **kwargs: {
            "executive_summary": "Weekly BESS memo synthesis.",
            "watchlist": ["Track capacity auction"],
        },
    )

    report = write_executive_summary(
        store,
        settings,
        scoring_provider="deepseek",
        scoring_model="deepseek-v4-flash",
        analysis_provider="openai",
        analysis_model="gpt-5.4-mini",
        write_latest_manifest=True,
    )

    assert report is not None
    assert report.scoring_provider == "deepseek"
    assert report.analysis_provider == "openai"
    body = report.markdown_path.read_text(encoding="utf-8")
    assert "## Executive Summary" in body
    assert "## Key Policy Updates" in body
    assert "METI announces capacity market reform" in body
    assert "## OCCTO / Grid Updates" in body
    assert "OCCTO publishes interconnection update" in body
    assert "## Competitor Movements" in body
    assert "Sumitomo invests in BESS platform" in body
    assert "## Financing / M&A / Platform Activity" in body
    assert "Itochu closes storage financing" in body
    assert "Impact on BESS" in body
    assert "Suggested Action" in body
    assert report.docx_path is not None and report.docx_path.exists()
    assert settings.latest_report_manifest_path.exists()

    tracker = store.list_tracker_items(
        profile_id="jp_storage",
        scoring_provider="deepseek",
        scoring_model="deepseek-v4-flash",
        analysis_provider="openai",
        analysis_model="gpt-5.4-mini",
    )
    assert len(tracker) >= 4
    assert all(item.status == "pending" for item in tracker)
    assert all(item.owner is None for item in tracker)
    categories = {item.category for item in tracker}
    assert "policy" in categories
    assert "occto_grid" in categories
    assert "competitors" in categories
    assert "financing_ma" in categories
