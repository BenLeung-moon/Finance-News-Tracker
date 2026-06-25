"""Profile registry and active-profile resolution."""

from __future__ import annotations

import os

from finance_news_tracker.profiles.base import TrackerProfile
from finance_news_tracker.profiles.jp_storage import PROFILE as JP_STORAGE_PROFILE
from finance_news_tracker.profiles.usdjpy import PROFILE as USDJPY_PROFILE

_PROFILES: dict[str, TrackerProfile] = {
    USDJPY_PROFILE.id: USDJPY_PROFILE,
    JP_STORAGE_PROFILE.id: JP_STORAGE_PROFILE,
}

DEFAULT_PROFILE_ID = "usdjpy"


def list_profiles() -> list[str]:
    return list(_PROFILES.keys())


def get_profile(profile_id: str | None = None) -> TrackerProfile:
    key = (profile_id or DEFAULT_PROFILE_ID).strip().lower()
    if key not in _PROFILES:
        known = ", ".join(sorted(_PROFILES))
        raise ValueError(f"Unknown TRACKER_PROFILE '{key}'. Known profiles: {known}")
    return _PROFILES[key]


def get_active_profile() -> TrackerProfile:
    return get_profile(os.getenv("TRACKER_PROFILE", DEFAULT_PROFILE_ID))
