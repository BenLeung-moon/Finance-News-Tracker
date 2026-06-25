from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from finance_news_tracker.config import Settings
from finance_news_tracker.collectors.enrich import enrich_from_html
from finance_news_tracker.collectors.html import collect_html
from finance_news_tracker.collectors.rss import collect_rss
from finance_news_tracker.collectors.utils import (
    content_hash,
    enrich_published_at,
    within_recency,
)
from finance_news_tracker.models import Article

logger = logging.getLogger(__name__)


def collect_all(
    settings: Settings,
    skip_hashes: set[str] | None = None,
) -> list[Article]:
    """Collect articles from all sources.

    ``skip_hashes`` are content hashes already in the store; items matching them
    are not HTML-enriched (we already have them), which keeps each article page
    to a single fetch across runs.
    """
    skip_hashes = skip_hashes or set()
    articles: list[Article] = []
    seen_hashes: set[str] = set()
    now = datetime.now(timezone.utc)
    headers = {"User-Agent": settings.user_agent}

    with httpx.Client(
        timeout=settings.request_timeout_seconds,
        headers=headers,
        follow_redirects=True,
    ) as client:
        for source in settings.sources:
            try:
                if source.kind == "rss":
                    items = collect_rss(source, settings)
                elif source.kind == "html":
                    items = collect_html(source, settings)
                else:
                    logger.warning("Unknown source kind: %s", source.kind)
                    continue
            except Exception:
                logger.exception("Failed to collect from %s", source.id)
                continue

            # RSS feeds list current headlines, so an undated item is treated as
            # first-seen-now (kept). HTML scrapes (NHK) keep the strict guard:
            # an undated item there may be an evergreen/old page, so it is dropped.
            allow_undated = source.kind == "rss"

            for item in items:
                h = item.content_hash or content_hash(
                    item.source, item.title, item.url
                )
                item.content_hash = h

                enrich_published_at(item)
                # Backfill date/excerpt the feed omitted from the article's HTML
                # head — but only for genuinely new items (avoid re-fetching).
                if item.published_at is None and h not in skip_hashes:
                    enrich_from_html(item, client)

                if item.published_at is None:
                    if not allow_undated:
                        continue
                elif not within_recency(item.published_at, settings.recency_hours):
                    continue
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                articles.append(item)

    # Undated items sort as "now" (fresh) rather than to the bottom.
    articles.sort(key=lambda a: a.published_at or now, reverse=True)
    logger.info("Collected %d unique articles within recency window", len(articles))
    return articles
