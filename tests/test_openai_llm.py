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


from tests.conftest import make_test_settings


def _settings(tmp_path: Path, *, openai_api_key: str = "") -> Settings:
    settings = make_test_settings(tmp_path, llm_provider="openai")
    settings.openai_api_key = openai_api_key
    return settings


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
