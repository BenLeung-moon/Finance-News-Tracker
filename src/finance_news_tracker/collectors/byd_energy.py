"""BYD Energy Storage news collector via official CMS JSON API.

The public HTML pages (https://www.bydenergy.com/en and /en/news) are JS SPAs
with no article links in the initial HTML. The site's own CMS API is used instead:

    POST https://cms-api.byd.com/es/search

中文注解：官网前端是 SPA，列表页无服务端文章链接；改用官网自身公开的 CMS JSON 接口。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

from finance_news_tracker.collectors.http import browser_headers
from finance_news_tracker.collectors.utils import content_hash
from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article
from finance_news_tracker.profiles.base import SourceConfig

logger = logging.getLogger(__name__)

# Public site origin used to absolute-ize relative article URLs from the API.
_SITE_ORIGIN = "https://www.bydenergy.com"

_DEFAULT_PAYLOAD = {
    "brandName": "energyStorage",
    "siteName": "en",
    "type": "news",
    "page": 1,
    "size": 20,
    "sortField": "date",
    "asc": False,
    "tags": [],
    "text": "",
    "year": "",
}


def _parse_api_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _records_to_articles(
    records: list[dict],
    source: SourceConfig,
) -> list[Article]:
    articles: list[Article] = []
    seen_urls: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue
        title = str(record.get("title") or "").strip()
        relative = str(record.get("url") or "").strip()
        if not title or not relative:
            continue

        url = urljoin(_SITE_ORIGIN, relative)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        published_at = _parse_api_date(record.get("date"))
        description = str(record.get("description") or "").strip()

        articles.append(
            Article(
                source=source.id,
                title=title,
                url=url,
                published_at=published_at,
                summary=description[:2000] if description else "",
                content_hash=content_hash(source.id, title, url),
                raw_excerpt=description[:500] if description else "",
            )
        )

    return articles


def collect_byd_energy(source: SourceConfig, settings: Settings) -> list[Article]:
    """Fetch BYD Energy Storage news from the official CMS search API."""
    headers = {
        **browser_headers(settings),
        "Content-Type": "application/json",
        "Origin": _SITE_ORIGIN,
        "Referer": f"{_SITE_ORIGIN}/en/news",
    }

    try:
        with httpx.Client(
            timeout=settings.request_timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = client.post(source.url, json=_DEFAULT_PAYLOAD)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Failed to fetch BYD Energy Storage news: %s", source.url)
        return []

    if not isinstance(payload, dict) or not payload.get("isSuccess"):
        logger.warning(
            "BYD Energy CMS API returned unsuccessful payload for %s: %s",
            source.id,
            payload.get("msg") if isinstance(payload, dict) else type(payload),
        )
        return []

    data = payload.get("data") or {}
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        logger.warning("BYD Energy CMS API missing records for %s", source.id)
        return []

    articles = _records_to_articles(records, source)
    logger.info("BYD Energy %s: %d items", source.id, len(articles))
    return articles
