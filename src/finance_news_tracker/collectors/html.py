from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from finance_news_tracker.collectors.utils import (
    content_hash,
    parse_date_from_text,
    parse_datetime_attr,
)
from finance_news_tracker.profiles.base import SourceConfig
from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article

logger = logging.getLogger(__name__)

SKIP_TITLE_PREFIXES = ("view all", "more", "next", "prev", "previous", "一覧", "戻る")
MIN_TITLE_LEN = 8


def resolve_source_urls(source: SourceConfig) -> list[str]:
    """Expand {year} placeholders when url_year_templated is set."""
    year = str(datetime.now().year)

    def _expand(url: str) -> str:
        if source.url_year_templated and "{year}" in url:
            return url.replace("{year}", year)
        return url

    return [_expand(source.url), *(_expand(u) for u in source.extra_urls)]


def _normalize_url(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    return urljoin(base_url, href)


def _same_site(href: str, page_url: str) -> bool:
    if href.startswith("/"):
        return True
    if not href.startswith("http"):
        return True
    return urlparse(href).netloc == urlparse(page_url).netloc


def _link_allowed(href: str, source: SourceConfig, page_url: str) -> bool:
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return False
    if not _same_site(href, page_url):
        return False

    for pat in source.exclude_patterns:
        if pat and pat in href:
            return False

    if source.link_patterns:
        return any(pat in href for pat in source.link_patterns)

    # No patterns: accept in-site links that look like article pages
    lowered = href.lower()
    if any(skip in lowered for skip in ("/index.html", "/index.htm", "/list/", "/tag/")):
        if not re.search(r"/\d{4}/", href):
            return False
    return True


def _extract_date_from_context(link, page_url: str) -> datetime | None:
    """Prefer <time datetime>, then parent text, then URL segments."""
    time_el = link.find("time")
    if time_el and time_el.get("datetime"):
        parsed = parse_datetime_attr(time_el["datetime"])
        if parsed:
            return parsed

    parent = link.find_parent(["article", "li", "div", "section", "tr", "dl"])
    if parent:
        for t in parent.find_all("time"):
            if t.get("datetime"):
                parsed = parse_datetime_attr(t["datetime"])
                if parsed:
                    return parsed
        context = parent.get_text(" ", strip=True)
        parsed = parse_date_from_text(context)
        if parsed:
            return parsed

    return parse_date_from_text(page_url)


def _extract_from_page(
    soup: BeautifulSoup, source: SourceConfig, page_url: str
) -> list[Article]:
    articles: list[Article] = []
    seen_urls: set[str] = set()
    base = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not _link_allowed(href, source, page_url):
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < MIN_TITLE_LEN:
            continue
        if title.lower().startswith(SKIP_TITLE_PREFIXES):
            continue

        url = _normalize_url(href, base)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        parent = link.find_parent(["article", "li", "div", "section"])
        context = parent.get_text(" ", strip=True) if parent else ""
        published_at = _extract_date_from_context(link, page_url)

        articles.append(
            Article(
                source=source.id,
                title=title,
                url=url,
                published_at=published_at,
                summary=context[:500] if context else "",
                content_hash=content_hash(source.id, title, url),
                raw_excerpt=context[:300],
            )
        )

    return articles


def collect_html(source: SourceConfig, settings: Settings) -> list[Article]:
    urls = resolve_source_urls(source)
    headers = {"User-Agent": settings.user_agent}
    all_articles: list[Article] = []
    seen_hashes: set[str] = set()

    with httpx.Client(
        timeout=settings.request_timeout_seconds,
        headers=headers,
        follow_redirects=True,
    ) as client:
        for page_url in urls:
            try:
                response = client.get(page_url)
                response.raise_for_status()
            except httpx.HTTPError:
                logger.exception("Failed to fetch HTML page: %s", page_url)
                continue

            soup = BeautifulSoup(response.text, "lxml")
            items = _extract_from_page(soup, source, page_url)
            for item in items:
                if item.content_hash in seen_hashes:
                    continue
                seen_hashes.add(item.content_hash)
                all_articles.append(item)

    logger.info("HTML %s: %d items", source.id, len(all_articles))
    return all_articles
