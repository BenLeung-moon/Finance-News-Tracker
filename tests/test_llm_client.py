import httpx

from finance_news_tracker.llm_client import chat_completion


class _FakeResponse:
    def __init__(self, status_code: int, data: dict | None = None):
        self.status_code = status_code
        self._data = data or {"choices": [{"message": {"content": "{}"}}]}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "https://api.example.com"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._data


def test_chat_completion_retries_transient_error(monkeypatch):
    calls = {"n": 0}

    def fake_post(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.RemoteProtocolError(
                "peer closed connection without sending complete message body"
            )
        return _FakeResponse(200)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        post = staticmethod(fake_post)

    monkeypatch.setattr("finance_news_tracker.llm_client.httpx.Client", FakeClient)
    monkeypatch.setattr("finance_news_tracker.llm_client.time.sleep", lambda *_: None)

    result = chat_completion(
        base_url="https://api.deepseek.com",
        api_key="test-key",
        payload={"model": "deepseek-chat", "messages": []},
        max_retries=3,
    )
    assert "choices" in result
    assert calls["n"] == 2
