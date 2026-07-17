"""Collector for エネハブ news list pages and article bodies."""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from finance_news_tracker.collectors.http import browser_headers
from finance_news_tracker.collectors.utils import content_hash, parse_date_from_text, within_recency
from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article
from finance_news_tracker.profiles.base import SourceConfig

logger = logging.getLogger(__name__)

_LIST_SELECTOR = ".elementor-element-2cc0520"
_CARD_SELECTOR = ".e-loop-item"
_BODY_SELECTOR = ".elementor-widget-theme-post-content"
_PAGE_PARAMETER = "e-page-2cc0520"
_MAX_PAGES = 50


def _page_url(url: str, page_number: int) -> str:
    """Return the Elementor pagination URL for a later news-list page."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[_PAGE_PARAMETER] = str(page_number)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _extract_list_items(
    soup: BeautifulSoup, source: SourceConfig
) -> list[tuple[str, str, object]]:
    """Extract unique article titles, URLs, and dates from the primary list only."""
    container = soup.select_one(_LIST_SELECTOR)
    if container is None:
        return []

    items: list[tuple[str, str, object]] = []
    seen_urls: set[str] = set()
    for card in container.select(_CARD_SELECTOR):
        link = next(
            (
                candidate
                for candidate in card.select("a[href]")
                if "/news/" in candidate["href"]
            ),
            None,
        )
        if link is None:
            continue

        title = link.get_text(" ", strip=True)
        url = link["href"].strip()
        if not title or not url or url in seen_urls:
            continue
        if source.link_patterns and not any(pattern in url for pattern in source.link_patterns):
            continue
        if any(pattern and pattern in url for pattern in source.exclude_patterns):
            continue

        time_el = card.find("time")
        published_at = parse_date_from_text(
            time_el.get_text(" ", strip=True) if time_el else ""
        )
        if published_at is None:
            continue
        seen_urls.add(url)
        items.append((title, url, published_at))
    return items


def _extract_article_body(html: str) -> str:
    """Return the article body without navigation or Elementor layout text."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.select_one(_BODY_SELECTOR)
    if body is None:
        return ""
    return " ".join(body.get_text(" ", strip=True).split())


def collect_enehub(source: SourceConfig, settings: Settings) -> list[Article]:
    """Collect recent エネハブ articles from the paginated list and detail pages."""
    articles: list[Article] = []
    seen_urls: set[str] = set()
    headers = browser_headers(settings)

    with httpx.Client(
        timeout=settings.request_timeout_seconds,
        headers=headers,
        follow_redirects=True,
    ) as client:
        for page_number in range(1, _MAX_PAGES + 1):
            list_url = source.url if page_number == 1 else _page_url(source.url, page_number)
            response = client.get(list_url)
            response.raise_for_status()
            items = _extract_list_items(BeautifulSoup(response.text, "lxml"), source)
            if not items:
                break

            page_has_recent_items = False
            for title, url, published_at in items:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                if not within_recency(published_at, settings.recency_hours):
                    continue
                page_has_recent_items = True

                try:
                    article_response = client.get(url)
                    article_response.raise_for_status()
                except httpx.HTTPError:
                    logger.exception("Failed to fetch エネハブ article: %s", url)
                    continue

                body = _extract_article_body(article_response.text)
                articles.append(
                    Article(
                        source=source.id,
                        title=title,
                        url=url,
                        published_at=published_at,
                        summary=body,
                        content_hash=content_hash(source.id, title, url),
                        raw_excerpt=body[:500],
                    )
                )

            # The list is reverse chronological, so later pages cannot be recent.
            if not page_has_recent_items:
                break

    logger.info("ENEHUB %s: %d items", source.id, len(articles))
    return articles
