from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import struct_time

import feedparser
import httpx
from bs4 import BeautifulSoup

from finance_news_tracker.collectors.utils import content_hash
from finance_news_tracker.config import SourceConfig, Settings
from finance_news_tracker.models import Article

logger = logging.getLogger(__name__)


def _parse_published(entry: dict) -> datetime | None:
    if entry.get("published_parsed"):
        st: struct_time = entry["published_parsed"]
        return datetime(*st[:6], tzinfo=timezone.utc)
    if entry.get("updated_parsed"):
        st = entry["updated_parsed"]
        return datetime(*st[:6], tzinfo=timezone.utc)
    published = entry.get("published") or entry.get("updated")
    if published:
        try:
            return parsedate_to_datetime(published)
        except (TypeError, ValueError):
            pass
    return None


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace from RSS description fields."""
    if not text or "<" not in text:
        return text.strip()
    soup = BeautifulSoup(text, "lxml")
    plain = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", plain).strip()


def _clean_summary(entry: dict) -> str:
    summary = entry.get("summary") or entry.get("description") or ""
    if hasattr(summary, "value"):
        summary = summary.value
    return _strip_html(str(summary))[:2000]


def collect_rss(source: SourceConfig, settings: Settings) -> list[Article]:
    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(timeout=settings.request_timeout_seconds, headers=headers) as client:
        response = client.get(source.url)
        response.raise_for_status()
        feed_text = response.text

    parsed = feedparser.parse(feed_text)
    articles: list[Article] = []

    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue

        published_at = _parse_published(entry)
        # Nikkei Asia 等源 RSS 常无日期字段：保留 None，不再伪造 now()。
        # 时效与排序改用 collected_at（首次抓取时刻）作近似，避免旧文被当成刚发布。
        summary = _clean_summary(entry)
        article = Article(
            source=source.id,
            title=title,
            url=url,
            published_at=published_at,
            summary=summary,
            content_hash=content_hash(source.id, title, url),
            raw_excerpt=summary[:500],
        )
        articles.append(article)

    logger.info("RSS %s: %d items", source.id, len(articles))
    return articles
