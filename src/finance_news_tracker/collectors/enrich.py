"""Backfill missing article fields (date, excerpt) from a page's public HTML head.

Some feeds — notably Nikkei Asia's public RSS — omit the publication date and a
usable summary. The article page's <head> still exposes this metadata
(``article:published_time``, JSON-LD ``datePublished``, ``meta[name=date]``,
``og:description`` …). Reading only the head metadata does NOT touch the
paywalled article body.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from finance_news_tracker.models import Article

logger = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    # datetime.fromisoformat (3.10) doesn't accept a trailing 'Z'.
    raw = re.sub(r"[Zz]$", "+00:00", raw)
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _date_candidates(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for prop in ("article:published_time", "article:modified_time", "og:updated_time"):
        for m in soup.find_all("meta", attrs={"property": prop}):
            content = m.get("content")
            if content:
                out.append(content)
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', text)
        if match:
            out.append(match.group(1))
    for name in ("date", "pubdate", "publishdate", "dc.date", "dc.date.issued"):
        for m in soup.find_all("meta", attrs={"name": name}):
            content = m.get("content")
            if content:
                out.append(content)
    time_el = soup.find("time")
    if time_el and time_el.get("datetime"):
        out.append(time_el["datetime"])
    return out


def _description(soup: BeautifulSoup) -> str | None:
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        m = soup.find("meta", attrs=attrs)
        if m and m.get("content"):
            text = m["content"].strip()
            if text:
                return text
    return None


def extract_metadata(html: str) -> tuple[datetime | None, str | None]:
    """Return (published_at, description) parsed from a page's HTML head."""
    soup = BeautifulSoup(html, "lxml")
    published: datetime | None = None
    for candidate in _date_candidates(soup):
        published = _parse_iso(candidate)
        if published:
            break
    return published, _description(soup)


def enrich_from_html(article: Article, client: httpx.Client) -> bool:
    """Fetch the article page and fill in missing published_at / summary.

    Returns True if anything was filled in. Failures are swallowed (best-effort).
    """
    try:
        response = client.get(article.url)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.debug("HTML enrich fetch failed: %s", article.url)
        return False

    published, description = extract_metadata(response.text)
    changed = False
    if published and article.published_at is None:
        article.published_at = published
        changed = True
    if description and not article.summary:
        article.summary = description[:2000]
        if not article.raw_excerpt:
            article.raw_excerpt = description[:500]
        changed = True
    if changed:
        logger.info("HTML-enriched %s (date=%s)", article.url, article.published_at)
    return changed
