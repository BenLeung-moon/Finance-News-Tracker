"""Centralized source labels, categories, and authority metadata."""

from __future__ import annotations

from typing import Literal

SourceCategory = Literal["official", "local_media", "international_media"]

SOURCE_LABELS: dict[str, str] = {
    "boj_whatsnew": "Bank of Japan",
    "boj_statistics": "BOJ Statistics",
    "nikkei_asia": "Nikkei Asia",
    "nhk_world": "NHK WORLD-JAPAN",
    "fed_press_monetary": "Federal Reserve (Monetary Policy)",
    "fed_speeches": "Federal Reserve (Speeches)",
    "us_treasury_press": "US Treasury",
    "fxstreet_news": "FXStreet",
    "investing_forex": "Investing.com (Forex)",
}

SOURCE_CATEGORIES: dict[str, SourceCategory] = {
    "boj_whatsnew": "official",
    "boj_statistics": "official",
    "fed_press_monetary": "official",
    "fed_speeches": "official",
    "us_treasury_press": "official",
    "nikkei_asia": "local_media",
    "nhk_world": "local_media",
    "fxstreet_news": "international_media",
    "investing_forex": "international_media",
}

# Higher = prefer when deduping or tie-breaking.
AUTHORITY_RANK: dict[SourceCategory, int] = {
    "official": 4,
    "local_media": 3,
    "international_media": 1,
}

INTERNATIONAL_MEDIA_SOURCES: frozenset[str] = frozenset(
    sid for sid, cat in SOURCE_CATEGORIES.items() if cat == "international_media"
)

OFFICIAL_SOURCES: frozenset[str] = frozenset(
    sid for sid, cat in SOURCE_CATEGORIES.items() if cat == "official"
)

LOCAL_MEDIA_SOURCES: frozenset[str] = frozenset(
    sid for sid, cat in SOURCE_CATEGORIES.items() if cat == "local_media"
)


def source_label(source_id: str) -> str:
    return SOURCE_LABELS.get(source_id, source_id)


def source_category(source_id: str) -> SourceCategory:
    return SOURCE_CATEGORIES.get(source_id, "local_media")


def authority_rank(source_id: str) -> int:
    return AUTHORITY_RANK.get(source_category(source_id), 2)


def is_official_source(source_id: str) -> bool:
    return source_id in OFFICIAL_SOURCES


def is_local_media_source(source_id: str) -> bool:
    return source_id in LOCAL_MEDIA_SOURCES


def is_international_media_source(source_id: str) -> bool:
    return source_id in INTERNATIONAL_MEDIA_SOURCES


def is_fx_media_source(source_id: str) -> bool:
    """Alias kept for compatibility with prefilter/dedupe call sites."""
    return is_international_media_source(source_id)
