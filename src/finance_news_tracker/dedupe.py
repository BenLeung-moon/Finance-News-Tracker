"""Text normalization and near-duplicate detection for news items."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from typing import Any

from finance_news_tracker.models import Article

# FXStreet / Investing.com — high-volume, repetitive feeds
FX_MEDIA_SOURCES: frozenset[str] = frozenset({"fxstreet_news", "investing_forex"})

_BOILERPLATE = re.compile(
    r"\b(breaking|update|live|analysis|forex|fx)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")


def is_fx_media_source(source: str) -> bool:
    return source in FX_MEDIA_SOURCES


def official_source_priority(source: str) -> int:
    """Higher = prefer keeping this item when stories are near-duplicates."""
    if source.startswith("boj") or source.startswith("fed_"):
        return 4
    if source.startswith("us_treasury_"):
        return 4
    if source in ("nikkei_asia", "nhk_world"):
        return 3
    if is_fx_media_source(source):
        return 1
    return 2


def article_text_blob(article: Article) -> str:
    return " ".join(
        filter(
            None,
            [article.title, article.summary, article.raw_excerpt],
        )
    )


def normalize_text(text: str) -> str:
    lower = text.lower()
    lower = _BOILERPLATE.sub(" ", lower)
    lower = _NON_ALNUM.sub(" ", lower)
    return re.sub(r"\s+", " ", lower).strip()


def text_similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def articles_similar(
    left: Article,
    right: Article,
    threshold: float,
) -> bool:
    blob_l = article_text_blob(left)
    blob_r = article_text_blob(right)
    if text_similarity(blob_l, blob_r) >= threshold:
        return True
    # Title-only match catches same headline, different URL/source
    return text_similarity(left.title, right.title) >= threshold


def pick_representative(
    current: Article,
    candidate: Article,
    *,
    current_priority: int,
    candidate_priority: int,
) -> Article:
    """Return the article to keep when two items are near-duplicates."""
    tier_c = official_source_priority(current.source)
    tier_n = official_source_priority(candidate.source)
    if tier_n > tier_c:
        return candidate
    if tier_c > tier_n:
        return current
    if candidate_priority > current_priority:
        return candidate
    if current_priority > candidate_priority:
        return current
    pub_c = current.published_at
    pub_n = candidate.published_at
    if pub_n and pub_c and pub_n > pub_c:
        return candidate
    return current


def dedupe_articles(
    ranked: list[tuple[Article, int, int]],
    threshold: float,
) -> list[tuple[Article, int, int]]:
    """Drop near-duplicates; keep official / higher-priority representatives."""
    kept: list[tuple[Article, int, int, Article]] = []

    for article, article_id, priority in ranked:
        merged = False
        for i, (rep, rep_id, rep_pri, _) in enumerate(kept):
            if not articles_similar(article, rep, threshold):
                continue
            winner = pick_representative(
                rep,
                article,
                current_priority=rep_pri,
                candidate_priority=priority,
            )
            if winner is article:
                kept[i] = (article, article_id, priority, article)
            merged = True
            break
        if not merged:
            kept.append((article, article_id, priority, article))

    return [(a, aid, pri) for a, aid, pri, _ in kept]


def apply_source_quotas(
    ranked: list[tuple[Article, int, int]],
    *,
    per_source_limits: dict[str, int],
    combined_media_limit: int | None,
    max_total: int,
) -> list[tuple[Article, int]]:
    """Cap items per source (and optional combined FX media cap)."""
    counts: dict[str, int] = {}
    media_total = 0
    result: list[tuple[Article, int]] = []

    for article, article_id, _priority in ranked:
        if len(result) >= max_total:
            break
        src = article.source
        limit = per_source_limits.get(src)
        if limit is not None and counts.get(src, 0) >= limit:
            continue
        if combined_media_limit is not None and is_fx_media_source(src):
            if media_total >= combined_media_limit:
                continue
        result.append((article, article_id))
        counts[src] = counts.get(src, 0) + 1
        if is_fx_media_source(src):
            media_total += 1

    return result


def scored_item_as_article(item: dict[str, Any]) -> Article:
    return Article(
        source=str(item.get("source", "")),
        title=str(item.get("title", "")),
        url=str(item.get("url", "")),
        summary=str(item.get("summary") or ""),
        raw_excerpt=str(item.get("why_it_matters") or item.get("summary") or "")[:500],
    )


def diversify_scored_items(
    items: list[dict[str, Any]],
    *,
    max_items: int,
    max_per_source: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """Pick diverse high-score items for executive summary / top stories."""
    kept: list[dict[str, Any]] = []
    kept_articles: list[Article] = []
    source_counts: dict[str, int] = {}

    for item in items:
        if len(kept) >= max_items:
            break
        src = str(item.get("source", ""))
        if source_counts.get(src, 0) >= max_per_source:
            continue
        article = scored_item_as_article(item)
        if any(
            articles_similar(article, prev, threshold) for prev in kept_articles
        ):
            continue
        kept.append(item)
        kept_articles.append(article)
        source_counts[src] = source_counts.get(src, 0) + 1

    return kept


def dedupe_scored_items(
    items: list[dict[str, Any]],
    threshold: float,
    *,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """Near-duplicate removal only (e.g. broader citation list)."""
    kept: list[dict[str, Any]] = []
    kept_articles: list[Article] = []

    for item in items:
        if max_items is not None and len(kept) >= max_items:
            break
        article = scored_item_as_article(item)
        if any(
            articles_similar(article, prev, threshold) for prev in kept_articles
        ):
            continue
        kept.append(item)
        kept_articles.append(article)

    return kept
