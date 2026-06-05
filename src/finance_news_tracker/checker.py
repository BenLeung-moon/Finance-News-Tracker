"""Portfolio-level news checker: category quotas, topic dedupe, final selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from finance_news_tracker.config import Settings
from finance_news_tracker.dedupe import articles_similar, scored_item_as_article
from finance_news_tracker.sources import (
    authority_rank,
    is_international_media_source,
    is_local_media_source,
    is_official_source,
    source_category,
)

_TOPIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "intervention_160",
        re.compile(
            r"\b(160|intervention|mof|finance ministry|takaichi)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "boj_hike",
        re.compile(
            r"\b(boj|bank of japan|ueda|rate hike|monetary policy|mpm)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fed_inflation",
        re.compile(
            r"\b(fed|federal reserve|fomc|powell|inflation|cpi|pce)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "rate_differential",
        re.compile(
            r"\b(carry trade|rate differential|yield|treasury|jgb|interest rate)\b",
            re.IGNORECASE,
        ),
    ),
]


@dataclass(frozen=True)
class SelectionPolicy:
    max_stories: int = 7
    max_citations: int = 15
    official_min_stories: int = 2
    international_media_max_stories: int = 2
    local_media_max_stories: int = 3
    max_per_source_stories: int = 2
    international_media_max_citations: int = 3
    international_media_topic_cap: int = 1


def policy_from_settings(settings: Settings) -> SelectionPolicy:
    return SelectionPolicy(
        max_stories=settings.summary_max_stories,
        max_citations=settings.summary_max_citations,
        official_min_stories=settings.checker_official_min,
        international_media_max_stories=settings.checker_intl_media_max_stories,
        local_media_max_stories=settings.checker_local_media_max_stories,
        max_per_source_stories=settings.summary_max_per_source,
        international_media_max_citations=settings.checker_intl_media_max_citations,
    )


def _item_blob(item: dict[str, Any]) -> str:
    return " ".join(
        filter(
            None,
            [
                str(item.get("title", "")),
                str(item.get("summary", "")),
                str(item.get("why_it_matters", "")),
                str(item.get("fx_channel", "")),
            ],
        )
    )


def topic_key(item: dict[str, Any]) -> str | None:
    """Group repeated market angles (e.g. 160 intervention, BoJ hike)."""
    blob = _item_blob(item)
    channel = str(item.get("fx_channel", "")).lower()
    if channel == "intervention":
        return "intervention_160"
    for key, pattern in _TOPIC_RULES:
        if pattern.search(blob):
            return key
    return None


def _category_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"official": 0, "local_media": 0, "international_media": 0}
    for item in items:
        cat = source_category(str(item.get("source", "")))
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def _source_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        src = str(item.get("source", ""))
        counts[src] = counts.get(src, 0) + 1
    return counts


def _topic_counts(
    items: list[dict[str, Any]],
    *,
    international_only: bool,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        src = str(item.get("source", ""))
        if international_only and not is_international_media_source(src):
            continue
        key = topic_key(item)
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _violates_story_caps(
    item: dict[str, Any],
    selected: list[dict[str, Any]],
    policy: SelectionPolicy,
) -> bool:
    src = str(item.get("source", ""))
    cat = source_category(src)
    cat_counts = _category_counts(selected)
    src_counts = _source_counts(selected)

    if src_counts.get(src, 0) >= policy.max_per_source_stories:
        return True
    if (
        cat == "international_media"
        and cat_counts.get("international_media", 0) >= policy.international_media_max_stories
    ):
        return True
    if cat == "local_media" and cat_counts.get("local_media", 0) >= policy.local_media_max_stories:
        return True

    if is_international_media_source(src):
        key = topic_key(item)
        if key:
            topic_counts = _topic_counts(selected, international_only=True)
            if topic_counts.get(key, 0) >= policy.international_media_topic_cap:
                return True
    return False


def _violates_citation_caps(
    item: dict[str, Any],
    selected: list[dict[str, Any]],
    policy: SelectionPolicy,
) -> bool:
    src = str(item.get("source", ""))
    cat_counts = _category_counts(selected)
    if (
        is_international_media_source(src)
        and cat_counts.get("international_media", 0) >= policy.international_media_max_citations
    ):
        return True
    return False


def _is_duplicate_of_selected(
    item: dict[str, Any],
    selected: list[dict[str, Any]],
    threshold: float,
) -> bool:
    article = scored_item_as_article(item)
    for prev in selected:
        if articles_similar(article, scored_item_as_article(prev), threshold):
            return True
    return False


def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    src = str(item.get("source", ""))
    return (
        _relevance_score(item),
        authority_rank(src),
        str(item.get("published_at") or item.get("collected_at") or ""),
    )


def _select_items(
    candidates: list[dict[str, Any]],
    *,
    settings: Settings,
    policy: SelectionPolicy,
    max_items: int,
    threshold: float,
    mode: str,
    official_reserve: int = 0,
) -> list[dict[str, Any]]:
    """Greedy selection with optional official minimum reservation."""
    selected: list[dict[str, Any]] = []
    remaining = list(candidates)

    if official_reserve > 0 and mode == "stories":
        official_pool = [
            item
            for item in remaining
            if is_official_source(str(item.get("source", "")))
            and _relevance_score(item) >= settings.min_relevance_score
        ]
        official_pool.sort(key=_sort_key, reverse=True)
        for item in official_pool:
            if len(selected) >= official_reserve:
                break
            if _is_duplicate_of_selected(item, selected, threshold):
                continue
            if _violates_story_caps(item, selected, policy):
                continue
            selected.append(item)
        remaining = [item for item in remaining if item not in selected]

    ranked = sorted(remaining, key=_sort_key, reverse=True)
    for item in ranked:
        if len(selected) >= max_items:
            break
        if _is_duplicate_of_selected(item, selected, threshold):
            continue
        if mode == "stories" and _violates_story_caps(item, selected, policy):
            continue
        if mode == "citations" and _violates_citation_caps(item, selected, policy):
            continue
        selected.append(item)

    return selected


def _relevance_score(item: dict[str, Any]) -> int:
    try:
        return int(item.get("relevance_score", 0))
    except (TypeError, ValueError):
        return 0


def select_summary_items(
    candidates: list[dict[str, Any]],
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Checker pass: curated top stories and citation list from scored pool."""
    policy = policy_from_settings(settings)
    threshold = settings.dedupe_similarity_threshold

    official_available = sum(
        1
        for item in candidates
        if is_official_source(str(item.get("source", "")))
        and _relevance_score(item) >= settings.min_relevance_score
    )
    official_reserve = min(policy.official_min_stories, official_available)

    story_items = _select_items(
        candidates,
        settings=settings,
        policy=policy,
        max_items=policy.max_stories,
        threshold=threshold,
        mode="stories",
        official_reserve=official_reserve,
    )

    citation_items = _select_items(
        candidates,
        settings=settings,
        policy=policy,
        max_items=policy.max_citations,
        threshold=threshold,
        mode="citations",
    )

    return story_items, citation_items
