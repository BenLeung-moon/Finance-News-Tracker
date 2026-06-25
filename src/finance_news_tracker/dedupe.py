"""Text normalization and near-duplicate detection for news items."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from typing import Any

from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article


def is_noisy_source(source_id: str, settings: Settings) -> bool:
    return source_id in settings.active_profile.noisy_source_ids


def source_priority_tier(source_id: str, settings: Settings) -> int:
    """Higher = prefer keeping this item when stories are near-duplicates."""
    source = settings.active_profile.source_by_id().get(source_id)
    if source is not None:
        return source.priority_tier
    return 2


def _boilerplate_pattern(settings: Settings) -> re.Pattern[str]:
    terms = settings.active_profile.boilerplate_terms
    if not terms:
        return re.compile(r"$^")  # match nothing
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)


def article_text_blob(article: Article) -> str:
    return " ".join(
        filter(
            None,
            [article.title, article.summary, article.raw_excerpt],
        )
    )


def normalize_text(text: str, settings: Settings) -> str:
    lower = text.lower()
    lower = _boilerplate_pattern(settings).sub(" ", lower)
    lower = re.sub(r"[^a-z0-9\s]+", " ", lower)
    return re.sub(r"\s+", " ", lower).strip()


def text_similarity(a: str, b: str, settings: Settings) -> float:
    na, nb = normalize_text(a, settings), normalize_text(b, settings)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def articles_similar(
    left: Article,
    right: Article,
    threshold: float,
    settings: Settings,
) -> bool:
    blob_l = article_text_blob(left)
    blob_r = article_text_blob(right)
    if text_similarity(blob_l, blob_r, settings) >= threshold:
        return True
    return text_similarity(left.title, right.title, settings) >= threshold


def pick_representative(
    current: Article,
    candidate: Article,
    *,
    current_priority: int,
    candidate_priority: int,
    settings: Settings,
) -> Article:
    """Return the article to keep when two items are near-duplicates."""
    tier_c = source_priority_tier(current.source, settings)
    tier_n = source_priority_tier(candidate.source, settings)
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
    settings: Settings,
) -> list[tuple[Article, int, int]]:
    """Drop near-duplicates; keep official / higher-priority representatives."""
    kept: list[tuple[Article, int, int, Article]] = []

    for article, article_id, priority in ranked:
        merged = False
        for i, (rep, rep_id, rep_pri, _) in enumerate(kept):
            if not articles_similar(article, rep, threshold, settings):
                continue
            winner = pick_representative(
                rep,
                article,
                current_priority=rep_pri,
                candidate_priority=priority,
                settings=settings,
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
    settings: Settings,
    *,
    max_total: int,
) -> list[tuple[Article, int]]:
    """Cap items per noisy source (and optional combined noisy cap)."""
    profile = settings.active_profile
    per_source_limits = {
        src: settings.noisy_score_limit_per_source
        for src in profile.noisy_source_ids
    }
    counts: dict[str, int] = {}
    noisy_total = 0
    result: list[tuple[Article, int]] = []

    for article, article_id, _priority in ranked:
        if len(result) >= max_total:
            break
        src = article.source
        limit = per_source_limits.get(src)
        if limit is not None and counts.get(src, 0) >= limit:
            continue
        if src in profile.noisy_source_ids:
            if noisy_total >= settings.noisy_score_limit_combined:
                continue
        result.append((article, article_id))
        counts[src] = counts.get(src, 0) + 1
        if src in profile.noisy_source_ids:
            noisy_total += 1

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
    settings: Settings,
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
            articles_similar(article, prev, threshold, settings) for prev in kept_articles
        ):
            continue
        kept.append(item)
        kept_articles.append(article)
        source_counts[src] = source_counts.get(src, 0) + 1

    return kept


def dedupe_scored_items(
    items: list[dict[str, Any]],
    threshold: float,
    settings: Settings,
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
            articles_similar(article, prev, threshold, settings) for prev in kept_articles
        ):
            continue
        kept.append(item)
        kept_articles.append(article)

    return kept


# Backward-compatible alias
FX_MEDIA_SOURCES = frozenset()  # populated at import via default settings if needed


def is_fx_media_source(source: str) -> bool:
    """Deprecated: use is_noisy_source with settings instead."""
    from finance_news_tracker.config import get_settings

    return is_noisy_source(source, get_settings())


def official_source_priority(source: str) -> int:
    """Deprecated: use source_priority_tier with settings instead."""
    from finance_news_tracker.config import get_settings

    return source_priority_tier(source, get_settings())
