from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx

from finance_news_tracker.collectors.byd_energy import (
    _records_to_articles,
    collect_byd_energy,
)
from finance_news_tracker.config import get_settings
from finance_news_tracker.profiles.base import SourceConfig


def _source() -> SourceConfig:
    return SourceConfig(
        id="byd_energy_news",
        name="BYD Energy Storage (News)",
        kind="byd_energy",
        url="https://cms-api.byd.com/es/search",
        languages=["en"],
        priority_tier=2,
    )


def test_records_to_articles_maps_fields():
    records = [
        {
            "title": "BYD Energy Storage Signs an 11.275GWh Contract with Masdar",
            "url": "/en/news/20260709",
            "date": "2026-07-09 00:00:00",
            "description": "Contract announcement",
        },
        {
            "title": "BYD Energy Storage Signs an 11.275GWh Contract with Masdar",
            "url": "/en/news/20260709",
            "date": "2026-07-09 00:00:00",
        },
        {
            "title": "",
            "url": "/en/news/missing-title",
            "date": "2026-07-01 00:00:00",
        },
    ]
    articles = _records_to_articles(records, _source())
    assert len(articles) == 1
    article = articles[0]
    assert article.source == "byd_energy_news"
    assert article.title.startswith("BYD Energy Storage Signs")
    assert article.url == "https://www.bydenergy.com/en/news/20260709"
    assert article.published_at == datetime(2026, 7, 9, tzinfo=timezone.utc)
    assert "Contract announcement" in article.summary


def test_collect_byd_energy_success(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    payload = {
        "code": 0,
        "isSuccess": True,
        "msg": "ok",
        "data": {
            "records": [
                {
                    "title": "Latin America's Largest Battery Storage Plant",
                    "url": "/en/news/20260615",
                    "date": "2026-06-15 00:00:00",
                    "description": "",
                }
            ],
            "total": 1,
            "pages": 1,
        },
    }

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = payload

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    with patch(
        "finance_news_tracker.collectors.byd_energy.httpx.Client",
        return_value=mock_client,
    ):
        articles = collect_byd_energy(_source(), settings)

    assert len(articles) == 1
    assert articles[0].url.endswith("/en/news/20260615")
    mock_client.post.assert_called_once()


def test_collect_byd_energy_http_error_returns_empty(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = httpx.HTTPError("boom")

    with patch(
        "finance_news_tracker.collectors.byd_energy.httpx.Client",
        return_value=mock_client,
    ):
        articles = collect_byd_energy(_source(), settings)

    assert articles == []


def test_collect_byd_energy_unsuccessful_payload(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "code": -1,
        "isSuccess": False,
        "msg": "系统错误",
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = mock_response

    with patch(
        "finance_news_tracker.collectors.byd_energy.httpx.Client",
        return_value=mock_client,
    ):
        articles = collect_byd_energy(_source(), settings)

    assert articles == []
