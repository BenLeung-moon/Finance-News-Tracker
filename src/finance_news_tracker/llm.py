from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from finance_news_tracker.config import Settings


ANTHROPIC_VERSION = "2023-06-01"

logger = logging.getLogger(__name__)

# OpenAI reasoning 系列前缀；gpt-5-chat* 仍走旧参数。
_OPENAI_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model: str
    api_key: str
    base_url: str


def openai_uses_max_completion_tokens(model: str) -> bool:
    """GPT-5 / o-series reasoning 模型需用 max_completion_tokens 而非 max_tokens。"""
    name = model.lower()
    if name.startswith("gpt-5-chat"):
        return False
    return any(name.startswith(prefix) for prefix in _OPENAI_REASONING_PREFIXES)


def openai_supports_temperature(model: str) -> bool:
    """Reasoning 模型不接受自定义 temperature；chat 变体与旧模型可以。"""
    return not openai_uses_max_completion_tokens(model)


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty model response")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def _openai_compatible_request(
    config: LlmConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    provider = config.provider.lower()
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    # 中文注解：OpenAI reasoning 与 DeepSeek/旧 OpenAI 参数互斥，不可同时发送。
    if provider == "openai" and openai_uses_max_completion_tokens(config.model):
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    return url, payload, headers


def _anthropic_request(
    config: LlmConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    url = f"{config.base_url.rstrip('/')}/messages"
    payload: dict[str, Any] = {
        "model": config.model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": config.api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    return url, payload, headers


def build_request(
    config: LlmConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    provider = config.provider.lower()
    if provider in {"deepseek", "openai"}:
        return _openai_compatible_request(
            config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "anthropic":
        return _anthropic_request(
            config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _parse_response(config: LlmConfig, data: dict[str, Any]) -> str:
    provider = config.provider.lower()
    if provider in {"deepseek", "openai"}:
        return str(data["choices"][0]["message"].get("content") or "")
    if provider == "anthropic":
        parts = data.get("content") or []
        text_parts = [
            str(part.get("text", ""))
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(text_parts)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _raise_for_status_with_body(response: httpx.Response, *, provider: str) -> None:
    if response.status_code < 400:
        return
    body = (response.text or "")[:500]
    logger.debug("%s API error (%s): %s", provider, response.status_code, body)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if body:
            raise httpx.HTTPStatusError(
                f"{exc}. Response body: {body}",
                request=exc.request,
                response=exc.response,
            ) from exc
        raise


def complete_json(
    config: LlmConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int = 1200,
    timeout_seconds: float = 120.0,
) -> tuple[dict[str, Any], str]:
    if not config.api_key:
        raise ValueError(
            f"{config.provider.upper()}_API_KEY is not set. "
            "Copy .env.example to .env and add the provider key."
        )

    url, payload, headers = build_request(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, json=payload, headers=headers)
        _raise_for_status_with_body(response, provider=config.provider)
        data = response.json()

    content = _parse_response(config, data)
    if not content.strip():
        raise ValueError(f"{config.provider} returned empty content")
    return extract_json(content), content


def test_llm_connectivity(
    config: LlmConfig,
    *,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    system_prompt = "Return only valid JSON."
    user_prompt = 'Return {"ok": true, "provider": "' + config.provider + '"}.'
    start = time.monotonic()
    url, payload, _headers = build_request(
        config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.0,
        max_tokens=80,
    )

    if not config.api_key:
        # 中文注解：无 key 时只验证本地配置和请求构造，不访问外部网络。
        return {
            "provider": config.provider,
            "model": config.model,
            "status": "dry_run",
            "missing_api_key": True,
            "network_call": False,
            "request_url": url,
            "payload_keys": sorted(payload.keys()),
        }

    try:
        parsed, _raw = complete_json(
            config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=80,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return {
            "provider": config.provider,
            "model": config.model,
            "status": "failed",
            "missing_api_key": False,
            "network_call": True,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "error": str(exc),
        }

    return {
        "provider": config.provider,
        "model": config.model,
        "status": "ok",
        "missing_api_key": False,
        "network_call": True,
        "latency_ms": int((time.monotonic() - start) * 1000),
        "response": parsed,
    }


def test_provider_llm(
    settings: Settings,
    provider: str | None = None,
    *,
    model: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """测试单个 LLM provider 的配置与连通性（无 key 时 dry_run，有 key 时发最小 JSON 请求）。"""
    config = settings.resolve_llm_config(provider, model)
    return test_llm_connectivity(config, timeout_seconds=timeout_seconds)
