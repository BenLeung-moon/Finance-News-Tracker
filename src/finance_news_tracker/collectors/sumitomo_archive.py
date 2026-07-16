from __future__ import annotations

import json
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from finance_news_tracker.collectors.html import resolve_source_urls
from finance_news_tracker.collectors.http import browser_headers
from finance_news_tracker.collectors.utils import content_hash, parse_date_from_text
from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article
from finance_news_tracker.profiles.base import SourceConfig

logger = logging.getLogger(__name__)


def _text_value(soup: BeautifulSoup, element_id: str, default: str = "") -> str:
    element = soup.find(id=element_id)
    if element and element.get("value"):
        return str(element["value"]).strip()
    return default


def _decode_payload(response: httpx.Response) -> dict:
    payload = response.json()
    if isinstance(payload, str):
        return json.loads(payload)
    if isinstance(payload, dict):
        return payload
    return {}


def _url_allowed(source: SourceConfig, url: str) -> bool:
    for pat in source.exclude_patterns:
        if pat and pat in url:
            return False
    if source.link_patterns:
        return any(pat in url for pat in source.link_patterns)
    return True


def _api_request_context(page_url: str) -> str:
    parsed = urlparse(page_url)
    return f"{parsed.netloc},{parsed.path}"


def collect_sumitomo_archive(
    source: SourceConfig, settings: Settings
) -> list[Article]:
    """Collect Sumitomo news pages rendered by the Sitecore NewsArchive API."""

    headers = browser_headers(settings)
    articles: list[Article] = []
    seen_urls: set[str] = set()

    with httpx.Client(
        timeout=settings.request_timeout_seconds,
        headers=headers,
        follow_redirects=True,
    ) as client:
        for page_url in resolve_source_urls(source):
            page = client.get(page_url)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, "lxml")

            parent_id = _text_value(soup, "selected-item-id")
            language = _text_value(soup, "context-language", "ja")
            split = _text_value(soup, "split-check", "False")
            if not parent_id:
                logger.warning("Sumitomo archive missing parentId: %s", page_url)
                continue

            api_url = urljoin(
                str(page.url), f"/api/SumitomoCorp/{language}/NewsArchive/GetNewsArchive"
            )
            response = client.post(
                api_url,
                data={
                    "parentId": parent_id,
                    "area": "",
                    "language": language,
                    "url": _api_request_context(str(page.url)),
                    "siteName": "",
                    "split": split,
                },
            )
            response.raise_for_status()
            payload = _decode_payload(response)

            for group in payload.get("GroupNews", []):
                for item in group.get("News", []):
                    title = (item.get("Title") or "").strip()
                    item_url = (item.get("Url") or "").strip()
                    if not title or not item_url:
                        continue
                    full_url = urljoin(str(page.url), item_url)
                    if not _url_allowed(source, full_url):
                        continue
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    published_text = (item.get("PublishDateStr") or "").strip()
                    summary = " ".join(filter(None, [published_text, title]))
                    articles.append(
                        Article(
                            source=source.id,
                            title=title,
                            url=full_url,
                            published_at=parse_date_from_text(published_text),
                            summary=summary,
                            content_hash=content_hash(source.id, title, full_url),
                            raw_excerpt=summary[:500],
                        )
                    )

    logger.info("SUMITOMO_ARCHIVE %s: %d items", source.id, len(articles))
    return articles
