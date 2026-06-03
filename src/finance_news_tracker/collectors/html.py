from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from finance_news_tracker.collectors.utils import content_hash
from finance_news_tracker.config import SourceConfig, Settings
from finance_news_tracker.models import Article

logger = logging.getLogger(__name__)

NHK_BASE = "https://www3.nhk.or.jp"
DATE_PATTERN = re.compile(
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},\s+\d{4}",
    re.IGNORECASE,
)


def _parse_nhk_date(text: str) -> datetime | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(match.group(0), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _normalize_url(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    return urljoin(base_url, href)


def _extract_from_page(soup: BeautifulSoup, source: SourceConfig, page_url: str) -> list[Article]:
    articles: list[Article] = []
    seen_urls: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if "/nhkworld/en/news/" not in href:
            continue
        # 排除 backstories 专题旧文，避免与“最新新闻”混淆
        if "/backstories/" in href:
            continue
        if any(skip in href for skip in ("/tags/", "/list/", "/video/", "/live_")):
            if not re.search(r"/news/[a-z0-9]", href):
                continue

        title = link.get_text(strip=True)
        if not title or len(title) < 12:
            continue

        url = _normalize_url(href, NHK_BASE)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        parent = link.find_parent(["article", "li", "div", "section"])
        context = parent.get_text(" ", strip=True) if parent else ""
        published_at = _parse_nhk_date(context) or _parse_nhk_date(page_url)

        article = Article(
            source=source.id,
            title=title,
            url=url,
            published_at=published_at,
            summary=context[:500] if context else "",
            content_hash=content_hash(source.id, title, url),
            raw_excerpt=context[:300],
        )
        articles.append(article)

    return articles


def collect_html(source: SourceConfig, settings: Settings) -> list[Article]:
    urls = [source.url, *source.extra_urls]
    headers = {"User-Agent": settings.user_agent}
    all_articles: list[Article] = []
    seen_hashes: set[str] = set()

    with httpx.Client(timeout=settings.request_timeout_seconds, headers=headers) as client:
        for page_url in urls:
            try:
                response = client.get(page_url)
                response.raise_for_status()
            except httpx.HTTPError:
                logger.exception("Failed to fetch NHK page: %s", page_url)
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
