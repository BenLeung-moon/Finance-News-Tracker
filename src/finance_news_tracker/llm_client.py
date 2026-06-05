"""Shared DeepSeek chat completions client with transient-error retries."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.PoolTimeout,
    httpx.NetworkError,
)

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: float = 120.0,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> dict[str, Any]:
    """POST /chat/completions; retry on dropped connections and 429/5xx."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        for attempt in range(1, max_retries + 1):
            try:
                response = client.post(url, json=payload, headers=headers)
                if (
                    response.status_code in _RETRYABLE_STATUS
                    and attempt < max_retries
                ):
                    logger.warning(
                        "DeepSeek HTTP %d (attempt %d/%d), retrying...",
                        response.status_code,
                        attempt,
                        max_retries,
                    )
                    time.sleep(retry_delay * attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except _TRANSIENT_ERRORS as exc:
                if attempt < max_retries:
                    logger.warning(
                        "DeepSeek transient error (attempt %d/%d): %s — retrying",
                        attempt,
                        max_retries,
                        exc,
                    )
                    time.sleep(retry_delay * attempt)
                    continue
                raise

    raise RuntimeError("chat_completion exhausted retries")
