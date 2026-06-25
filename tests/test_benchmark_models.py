from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article
from finance_news_tracker.pipeline import run_once
from finance_news_tracker.store import Store

_BENCHMARK_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "benchmark_models.py"
)


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location(
        "benchmark_models",
        _BENCHMARK_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["benchmark_models"] = module
    spec.loader.exec_module(module)
    return module


def _settings(tmp_path: Path, *, llm_provider: str = "deepseek") -> Settings:
    data_dir = tmp_path / "data"
    summaries_dir = tmp_path / "summaries"
    log_dir = tmp_path / "logs"
    for directory in (data_dir, summaries_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return Settings(
        llm_provider=llm_provider,
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com/v1",
        deepseek_model="deepseek-v4-flash",
        openai_api_key="",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-5.4-mini",
        anthropic_api_key="",
        anthropic_base_url="https://api.anthropic.com/v1",
        anthropic_model="claude-haiku-4-5-20251001",
        data_dir=data_dir,
        summaries_dir=summaries_dir,
        log_dir=log_dir,
        recency_hours=72,
        min_relevance_score=40,
        max_articles_to_score=25,
        request_timeout_seconds=30,
        user_agent="test",
        run_timezone="Asia/Hong_Kong",
        run_weekdays_only=True,
        holiday_guard_enabled=False,
        report_retention_days=90,
        log_level="INFO",
        email_enabled=False,
        smtp_host="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        email_from="",
        email_to=[],
        email_subject_prefix="[Test]",
        email_attach_docx=True,
    )


def _article(content_hash: str) -> Article:
    return Article(
        source="nikkei_asia",
        title=f"USD/JPY article {content_hash}",
        url=f"https://example.com/{content_hash}",
        published_at=datetime.now(timezone.utc),
        summary="Fed and BOJ rate expectations move USD/JPY.",
        content_hash=content_hash,
    )


def test_model_benchmark_freezes_ranked_article_set_once(monkeypatch, tmp_path: Path):
    benchmark_models = _load_benchmark_module()
    settings = _settings(tmp_path)
    store = Store(settings.db_path)
    store.upsert_article(_article("a"))
    store.upsert_article(_article("b"))
    calls = {"rank": 0}

    def fake_rank(items: list[tuple[Article, int]], settings: Settings):
        calls["rank"] += 1
        return list(items)[:1]

    monkeypatch.setattr(benchmark_models, "get_settings", lambda: settings)
    monkeypatch.setattr(benchmark_models, "get_store", lambda s: store)
    monkeypatch.setattr(benchmark_models, "rank_for_scoring", fake_rank)

    summaries = benchmark_models.run_model_benchmark(dry_run=True)

    assert calls["rank"] == 1
    assert [summary.provider for summary in summaries] == [
        "deepseek",
        "openai",
        "anthropic",
    ]
    assert all(summary.attempted == 1 for summary in summaries)


def test_run_once_uses_same_provider_model_for_score_and_summary(
    monkeypatch,
    tmp_path: Path,
):
    settings = _settings(tmp_path, llm_provider="deepseek")
    captured: dict[str, str | None] = {"score_provider": None, "summary_model": None}

    monkeypatch.setattr("finance_news_tracker.pipeline.get_settings", lambda: settings)
    monkeypatch.setattr(
        "finance_news_tracker.pipeline.run_collect",
        lambda: {"articles": 1, "score_rows": 0, "new_this_run": 1},
    )

    def fake_run_score(provider=None, model=None, **kwargs):
        captured["score_provider"] = provider
        captured["score_model"] = model
        return 1

    def fake_run_summarize(provider=None, model=None, **kwargs):
        captured["summary_provider"] = provider
        captured["summary_model"] = model
        captured["write_latest_manifest"] = kwargs.get("write_latest_manifest")
        from finance_news_tracker.manifest import GeneratedReport

        return GeneratedReport(
            run_id="20260625_120000",
            markdown_path=settings.summaries_dir / "report.md",
            docx_path=None,
            created_at=datetime.now(timezone.utc),
            story_count=1,
            article_count=1,
            provider=provider or "deepseek",
            model=model or "custom-model",
        )

    monkeypatch.setattr("finance_news_tracker.pipeline.run_score", fake_run_score)
    monkeypatch.setattr("finance_news_tracker.pipeline.run_summarize", fake_run_summarize)

    report = run_once(provider="openai", model="custom-model")

    assert report is not None
    assert captured["score_provider"] == "openai"
    assert captured["score_model"] == "custom-model"
    assert captured["summary_provider"] == "openai"
    assert captured["summary_model"] == "custom-model"
    assert captured["write_latest_manifest"] is True
