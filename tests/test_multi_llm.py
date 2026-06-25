from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finance_news_tracker.config import Settings
from finance_news_tracker.llm import (
    LlmConfig,
    complete_json,
    test_llm_connectivity as llm_connectivity_self_test,
)
from finance_news_tracker.models import Article, ScoreResult
from finance_news_tracker.pipeline import run_score_test_all
from finance_news_tracker.run_scheduled import run_collect_scheduled_workflow
from finance_news_tracker.store import Store
from finance_news_tracker.summary import write_executive_summary


def _settings(tmp_path: Path, *, llm_provider: str = "deepseek") -> Settings:
    data_dir = tmp_path / "data"
    summaries_dir = tmp_path / "summaries"
    log_dir = tmp_path / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
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


def _score(article_id: int, provider: str, model: str) -> ScoreResult:
    return ScoreResult(
        article_id=article_id,
        relevance_score=80,
        fx_channel="monetary_policy",
        likely_usdjpy_direction="usd_jpy_up",
        confidence="high",
        summary="Policy divergence matters.",
        why_it_matters="Rate spreads can move USD/JPY.",
        source_citation="Test",
        provider=provider,
        model=model,
    )


def test_resolve_none_uses_active_provider_not_all_providers(tmp_path: Path):
    settings = _settings(tmp_path, llm_provider="openai")

    config = settings.resolve_llm_config()

    assert config.provider == "openai"
    assert config.model == "gpt-5.4-mini"


def test_llm_connectivity_without_api_key_does_not_call_network():
    result = llm_connectivity_self_test(
        LlmConfig(
            provider="anthropic",
            model="claude-test",
            api_key="",
            base_url="https://api.anthropic.com/v1",
        )
    )

    assert result["status"] == "dry_run"
    assert result["missing_api_key"] is True
    assert result["network_call"] is False
    assert "response_format" not in result["payload_keys"]


class _FakeResponse:
    def __init__(self, data: dict[str, Any]):
        self._data = data
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._data


class _FakeClient:
    response_data: dict[str, Any]

    def __init__(self, *args: Any, **kwargs: Any):
        return None

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(self.response_data)


def test_complete_json_anthropic_with_mocked_response(monkeypatch):
    _FakeClient.response_data = {
        "content": [{"type": "text", "text": 'Before {"ok": true} after'}],
    }
    monkeypatch.setattr("finance_news_tracker.llm.httpx.Client", _FakeClient)

    parsed, raw = complete_json(
        LlmConfig(
            provider="anthropic",
            model="claude-test",
            api_key="key",
            base_url="https://api.anthropic.com/v1",
        ),
        system_prompt="Return JSON.",
        user_prompt="Return ok.",
        temperature=0,
    )

    assert parsed == {"ok": True}
    assert "Before" in raw


def test_test_all_freezes_ranked_article_set_once(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)
    store = Store(settings.db_path)
    store.upsert_article(_article("a"))
    store.upsert_article(_article("b"))
    calls = {"rank": 0}

    def fake_rank(items: list[tuple[Article, int]], settings: Settings):
        calls["rank"] += 1
        return list(items)[:1]

    monkeypatch.setattr("finance_news_tracker.pipeline.get_settings", lambda: settings)
    monkeypatch.setattr("finance_news_tracker.pipeline.rank_for_scoring", fake_rank)

    summaries = run_score_test_all(dry_run=True)

    assert calls["rank"] == 1
    assert [summary.provider for summary in summaries] == [
        "deepseek",
        "openai",
        "anthropic",
    ]
    assert all(summary.attempted == 1 for summary in summaries)


def test_provider_summary_does_not_overwrite_latest_manifest(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)
    store = Store(settings.db_path)
    aid, _ = store.upsert_article(_article("summary"))
    store.save_score(_score(aid, "openai", "gpt-5.4-mini"))

    monkeypatch.setattr(
        "finance_news_tracker.summary.generate_executive_summary_llm",
        lambda *args, **kwargs: {"market_read": "Test read", "watchlist": ["CPI"]},
    )
    monkeypatch.setattr(
        "finance_news_tracker.summary.write_word_summary",
        lambda *args, **kwargs: None,
    )

    report = write_executive_summary(
        store,
        settings,
        provider="openai",
        model="gpt-5.4-mini",
        write_latest_manifest=False,
    )

    assert report is not None
    assert "openai_gpt-5.4-mini" in report.markdown_path.name
    assert not settings.latest_report_manifest_path.exists()


def test_collect_scheduled_records_collect_only_history(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path)

    monkeypatch.setattr("finance_news_tracker.run_scheduled.get_settings", lambda: settings)
    monkeypatch.setattr("finance_news_tracker.run_scheduled.should_run_scheduled", lambda s: True)
    monkeypatch.setattr(
        "finance_news_tracker.run_scheduled.run_collect",
        lambda: {"articles": 3, "new_this_run": 2},
    )

    stats = run_collect_scheduled_workflow(settings)

    assert stats == {"articles": 3, "new_this_run": 2}
    store = Store(settings.db_path)
    with store._conn() as conn:
        row = conn.execute("SELECT * FROM run_history").fetchone()
    assert row["trigger_type"] == "collect-scheduled"
    assert row["llm_model"] == "collect-only"
