"""Scoring vs Analysis LLM role configuration and lineage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from finance_news_tracker.models import Article, ScoreResult
from finance_news_tracker.pipeline import run_once
from finance_news_tracker.store import Store
from finance_news_tracker.summary import write_executive_summary
from tests.conftest import make_test_settings


def test_resolve_scoring_and_analysis_can_differ(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SCORING_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("SCORING_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("ANALYSIS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("ANALYSIS_LLM_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    from finance_news_tracker.config import get_settings

    settings = get_settings()
    # Override dirs so we do not touch real data
    settings = make_test_settings(tmp_path, llm_provider="anthropic")
    settings.scoring_llm_provider = "deepseek"
    settings.scoring_llm_model = "deepseek-v4-flash"
    settings.analysis_llm_provider = "openai"
    settings.analysis_llm_model = "gpt-5.4-mini"

    scoring = settings.resolve_scoring_llm_config()
    analysis = settings.resolve_analysis_llm_config()

    assert scoring.provider == "deepseek"
    assert scoring.model == "deepseek-v4-flash"
    assert analysis.provider == "openai"
    assert analysis.model == "gpt-5.4-mini"


def test_role_fallback_uses_llm_provider(tmp_path: Path):
    settings = make_test_settings(tmp_path, llm_provider="openai")
    scoring = settings.resolve_scoring_llm_config()
    analysis = settings.resolve_analysis_llm_config()
    assert scoring.provider == "openai"
    assert analysis.provider == "openai"
    assert scoring.model == settings.openai_model
    assert analysis.model == settings.openai_model


def test_run_once_passes_distinct_role_models(monkeypatch, tmp_path: Path):
    settings = make_test_settings(tmp_path, llm_provider="deepseek")
    captured: dict[str, str | None] = {}

    monkeypatch.setattr("finance_news_tracker.pipeline.get_settings", lambda: settings)
    monkeypatch.setattr(
        "finance_news_tracker.pipeline.run_collect",
        lambda: {"articles": 1, "score_rows": 0, "new_this_run": 1},
    )

    def fake_run_score(provider=None, model=None, **kwargs):
        captured["score_provider"] = provider
        captured["score_model"] = model
        return 1

    def fake_run_summarize(**kwargs):
        captured.update(kwargs)
        from finance_news_tracker.manifest import GeneratedReport

        return GeneratedReport(
            run_id="20260716_120000",
            markdown_path=settings.summaries_dir / "report.md",
            docx_path=None,
            created_at=datetime.now(timezone.utc),
            story_count=1,
            article_count=1,
            provider=kwargs.get("analysis_provider") or "openai",
            model=kwargs.get("analysis_model") or "gpt-test",
            scoring_provider=kwargs.get("scoring_provider") or "deepseek",
            scoring_model=kwargs.get("scoring_model") or "flash",
            analysis_provider=kwargs.get("analysis_provider") or "openai",
            analysis_model=kwargs.get("analysis_model") or "gpt-test",
        )

    monkeypatch.setattr("finance_news_tracker.pipeline.run_score", fake_run_score)
    monkeypatch.setattr("finance_news_tracker.pipeline.run_summarize", fake_run_summarize)

    report = run_once(
        scoring_provider="deepseek",
        scoring_model="flash",
        analysis_provider="openai",
        analysis_model="gpt-test",
    )

    assert report is not None
    assert captured["score_provider"] == "deepseek"
    assert captured["score_model"] == "flash"
    assert captured["scoring_provider"] == "deepseek"
    assert captured["scoring_model"] == "flash"
    assert captured["analysis_provider"] == "openai"
    assert captured["analysis_model"] == "gpt-test"


def test_summary_reads_only_scoring_model_scores(monkeypatch, tmp_path: Path):
    settings = make_test_settings(tmp_path)
    store = Store(settings.db_path)
    article = Article(
        source="nikkei_asia",
        title="BOJ holds rates",
        url="https://example.com/boj",
        published_at=datetime.now(timezone.utc),
        summary="Policy hold",
        content_hash="role-lineage",
    )
    aid, _ = store.upsert_article(article)
    store.save_score(
        ScoreResult(
            article_id=aid,
            relevance_score=90,
            category="monetary_policy",
            signal="usd_jpy_up",
            confidence="high",
            summary="Hold",
            why_it_matters="Rates",
            source_citation="t",
            provider="deepseek",
            model="deepseek-v4-flash",
        )
    )
    store.save_score(
        ScoreResult(
            article_id=aid,
            relevance_score=10,
            category="other",
            signal="unclear",
            confidence="low",
            summary="Noise",
            why_it_matters="n/a",
            source_citation="t",
            provider="openai",
            model="gpt-5.4-mini",
        )
    )

    monkeypatch.setattr(
        "finance_news_tracker.summary.analyze_items_batch",
        lambda items, settings, **kwargs: [],
    )
    monkeypatch.setattr(
        "finance_news_tracker.summary.generate_executive_summary_llm",
        lambda *args, **kwargs: {"market_read": "ok", "watchlist": ["a"]},
    )
    monkeypatch.setattr(
        "finance_news_tracker.summary.write_word_summary",
        lambda *args, **kwargs: None,
    )

    report = write_executive_summary(
        store,
        settings,
        scoring_provider="deepseek",
        scoring_model="deepseek-v4-flash",
        analysis_provider="openai",
        analysis_model="gpt-5.4-mini",
        write_latest_manifest=False,
    )
    assert report is not None
    assert report.scoring_provider == "deepseek"
    assert report.analysis_provider == "openai"
    body = report.markdown_path.read_text(encoding="utf-8")
    assert "BOJ holds rates" in body
    assert "Scoring LLM:** deepseek" in body
    assert "Analysis LLM:** openai" in body
