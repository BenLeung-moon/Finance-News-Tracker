from __future__ import annotations

from pathlib import Path

import pytest

from finance_news_tracker.config import Settings
from finance_news_tracker.llm import (
    LlmConfig,
    build_request,
    complete_json,
    openai_supports_temperature,
    openai_uses_max_completion_tokens,
    test_provider_llm as run_provider_llm_test,
)
from tests.llm_test_helpers import CapturingFakeClient


def _settings(tmp_path: Path, *, openai_api_key: str = "") -> Settings:
    data_dir = tmp_path / "data"
    summaries_dir = tmp_path / "summaries"
    log_dir = tmp_path / "logs"
    for directory in (data_dir, summaries_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return Settings(
        llm_provider="openai",
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com/v1",
        deepseek_model="deepseek-v4-flash",
        openai_api_key=openai_api_key,
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


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5.4-mini", True),
        ("gpt-5-mini", True),
        ("o3-mini", True),
        ("gpt-5-chat-latest", False),
        ("gpt-4o-mini", False),
    ],
)
def test_openai_uses_max_completion_tokens_model_matrix(model: str, expected: bool):
    assert openai_uses_max_completion_tokens(model) is expected
    assert openai_supports_temperature(model) is (not expected)


def test_gpt54_mini_payload_uses_max_completion_tokens():
    _url, payload, _headers = build_request(
        LlmConfig(
            provider="openai",
            model="gpt-5.4-mini",
            api_key="key",
            base_url="https://api.openai.com/v1",
        ),
        system_prompt="sys",
        user_prompt="user",
        temperature=0.2,
        max_tokens=80,
    )

    assert payload["max_completion_tokens"] == 80
    assert "max_tokens" not in payload
    assert "temperature" not in payload


def test_gpt4o_mini_payload_uses_legacy_max_tokens():
    _url, payload, _headers = build_request(
        LlmConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key="key",
            base_url="https://api.openai.com/v1",
        ),
        system_prompt="sys",
        user_prompt="user",
        temperature=0.2,
        max_tokens=80,
    )

    assert payload["max_tokens"] == 80
    assert payload["temperature"] == 0.2
    assert "max_completion_tokens" not in payload


def test_deepseek_payload_unchanged():
    _url, payload, _headers = build_request(
        LlmConfig(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="key",
            base_url="https://api.deepseek.com/v1",
        ),
        system_prompt="sys",
        user_prompt="user",
        temperature=0.2,
        max_tokens=80,
    )

    assert payload["max_tokens"] == 80
    assert payload["temperature"] == 0.2
    assert "max_completion_tokens" not in payload


def test_provider_llm_openai_dry_run_without_key(tmp_path: Path):
    settings = _settings(tmp_path)

    result = run_provider_llm_test(settings, "openai")

    assert result["status"] == "dry_run"
    assert result["missing_api_key"] is True
    assert result["network_call"] is False
    assert "max_completion_tokens" in result["payload_keys"]
    assert "max_tokens" not in result["payload_keys"]
    assert "temperature" not in result["payload_keys"]


def test_provider_llm_openai_mocked_ok(monkeypatch, tmp_path: Path):
    settings = _settings(tmp_path, openai_api_key="key")
    CapturingFakeClient.response_data = {
        "choices": [{"message": {"content": '{"ok": true, "provider": "openai"}'}}],
    }
    monkeypatch.setattr("finance_news_tracker.llm.httpx.Client", CapturingFakeClient)

    result = run_provider_llm_test(settings, "openai")

    assert result["status"] == "ok"
    assert result["response"] == {"ok": True, "provider": "openai"}
    assert CapturingFakeClient.last_payload is not None
    assert "max_completion_tokens" in CapturingFakeClient.last_payload
    assert "temperature" not in CapturingFakeClient.last_payload


def test_complete_json_openai_gpt54_with_mocked_response(monkeypatch):
    CapturingFakeClient.response_data = {
        "choices": [{"message": {"content": '{"ok": true}'}}],
    }
    monkeypatch.setattr("finance_news_tracker.llm.httpx.Client", CapturingFakeClient)

    parsed, raw = complete_json(
        LlmConfig(
            provider="openai",
            model="gpt-5.4-mini",
            api_key="key",
            base_url="https://api.openai.com/v1",
        ),
        system_prompt="Return JSON.",
        user_prompt="Return ok.",
        temperature=0,
    )

    assert parsed == {"ok": True}
    assert raw == '{"ok": true}'
    assert CapturingFakeClient.last_payload is not None
    assert CapturingFakeClient.last_payload.get("max_completion_tokens") == 1200
