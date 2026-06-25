from __future__ import annotations

import re

from datetime import datetime, timezone

from finance_news_tracker.config import Settings
from finance_news_tracker.dedupe import (
    apply_source_quotas,
    dedupe_articles,
    is_noisy_source,
    source_priority_tier,
)
from finance_news_tracker.models import Article, ScoredArticle


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    hits = []
    for kw in keywords:
        if kw.lower() in lower:
            hits.append(kw)
    return hits


def _tier_keywords(profile, tier: str) -> list[str]:
    return profile.keyword_tiers.get(tier, [])


def _noisy_prefilter(blob: str, settings: Settings) -> tuple[bool, list[str]]:
    """Stricter gate for high-volume noisy sources."""
    profile = settings.active_profile
    direct = keyword_hits(blob, _tier_keywords(profile, "direct"))
    if direct:
        return True, direct

    strong = keyword_hits(blob, _tier_keywords(profile, "strong"))
    if len(strong) >= 2:
        return True, strong

    general = keyword_hits(blob, settings.keywords)
    weak = keyword_hits(blob, _tier_keywords(profile, "weak"))
    if general and not weak:
        return True, general
    if general and len(general) > len(weak):
        non_weak = [h for h in general if h not in weak]
        if non_weak:
            return True, non_weak

    return False, []


def _storage_prefilter(blob: str, settings: Settings) -> tuple[bool, list[str]]:
    """Keyword gate for jp_storage profile (policy/project/company tiers)."""
    profile = settings.active_profile
    for tier in ("policy", "project", "company"):
        hits = keyword_hits(blob, _tier_keywords(profile, tier))
        if hits:
            return True, hits
    general = keyword_hits(blob, _tier_keywords(profile, "general"))
    return (bool(general), general)


def prefilter_article(article: Article, settings: Settings) -> tuple[bool, list[str]]:
    blob = " ".join(
        filter(
            None,
            [article.title, article.summary, article.raw_excerpt],
        )
    )

    profile = settings.active_profile

    if is_noisy_source(article.source, settings):
        return _noisy_prefilter(blob, settings)

    if profile.id == "jp_storage":
        hit, hits = _storage_prefilter(blob, settings)
        if hit:
            return True, hits
    else:
        hits = keyword_hits(blob, settings.keywords)
        if hits:
            return True, hits

    for rule in profile.title_fallback_rules:
        if article.source.startswith(rule.source_prefix):
            if re.search(rule.pattern, article.title, re.IGNORECASE):
                return True, [rule.tag]

    return False, []


def _priority_for_article(article: Article, hit: bool, hits: list[str], settings: Settings) -> int:
    profile = settings.active_profile
    priority = len(hits)

    priority += source_priority_tier(article.source, settings)

    # Bonus when high-priority keyword tiers matched
    blob = " ".join(hits).lower()
    for tier in profile.high_priority_tiers:
        for kw in _tier_keywords(profile, tier):
            if kw.lower() in blob:
                priority += 3
                break

    if hit:
        priority += 2

    if is_noisy_source(article.source, settings):
        priority = max(0, priority - 1)

    return priority


def rank_for_scoring(
    articles: list[tuple[Article, int]],
    settings: Settings,
) -> list[tuple[Article, int]]:
    """Return articles prioritized for provider/model scoring."""

    scored: list[tuple[Article, int, int, list[str]]] = []
    for article, article_id in articles:
        hit, hits = prefilter_article(article, settings)
        if is_noisy_source(article.source, settings) and not hit:
            continue
        priority = _priority_for_article(article, hit, hits, settings)
        scored.append((article, article_id, priority, hits))

    now = datetime.now(timezone.utc)

    def _sort_key(item: tuple[Article, int, int, list[str]]) -> tuple[int, datetime]:
        article = item[0]
        pub = article.published_at
        if pub is None:
            pub = now
        elif pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return (item[2], pub)

    scored.sort(key=_sort_key, reverse=True)

    ranked_triples = [(a, aid, pri) for a, aid, pri, _ in scored]
    deduped = dedupe_articles(
        ranked_triples, settings.dedupe_similarity_threshold, settings
    )

    limited = apply_source_quotas(
        deduped,
        settings,
        max_total=settings.max_articles_to_score,
    )
    return limited


def build_scored_articles(
    articles: list[tuple[Article, int]],
    settings: Settings,
) -> list[ScoredArticle]:
    result: list[ScoredArticle] = []
    for article, article_id in articles:
        hit, hits = prefilter_article(article, settings)
        result.append(
            ScoredArticle(
                article=article,
                article_id=article_id,
                prefilter_hit=hit,
                keyword_hits=hits,
            )
        )
    return result
