from __future__ import annotations

from typing import Any


class FakeResponse:
    def __init__(self, data: dict[str, Any], *, status_code: int = 200, text: str = ""):
        self._data = data
        self.status_code = status_code
        self.text = text or ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "https://example.com"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict[str, Any]:
        return self._data


class CapturingFakeClient:
    """Mock httpx.Client that records the last POST json payload."""

    response_data: dict[str, Any] = {}
    last_payload: dict[str, Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any):
        return None

    def __enter__(self) -> CapturingFakeClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
        payload = kwargs.get("json")
        if isinstance(payload, dict):
            CapturingFakeClient.last_payload = payload
        return FakeResponse(self.response_data)
