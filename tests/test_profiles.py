from finance_news_tracker.config import get_settings
from finance_news_tracker.profiles import get_profile, list_profiles
import pytest


def test_list_profiles():
    ids = list_profiles()
    assert ids == ["usdjpy"]


def test_get_profile_defaults_to_usdjpy():
    profile = get_profile()
    assert profile.id == "usdjpy"
    assert len(profile.sources) == 9


def test_unknown_profile_raises():
    with pytest.raises(ValueError, match="Unknown TRACKER_PROFILE"):
        get_profile("jp_storage")


def test_settings_loads_active_profile():
    settings = get_settings()
    assert settings.active_profile.id == settings.tracker_profile_id
    assert settings.sources == settings.active_profile.sources


def test_settings_uses_profile_recency_default(monkeypatch):
    monkeypatch.delenv("RECENCY_HOURS", raising=False)
    monkeypatch.setenv("TRACKER_PROFILE", "usdjpy")

    settings = get_settings()

    assert settings.recency_hours == 72


def test_blank_recency_env_uses_profile_default(monkeypatch):
    """An explicitly blank .env value must not override the profile default.

    中文注解：RECENCY_HOURS=（空值）应使用当前 Profile 的默认回看窗口。
    """
    monkeypatch.setenv("RECENCY_HOURS", "")
    monkeypatch.setenv("TRACKER_PROFILE", "usdjpy")

    settings = get_settings()

    assert settings.recency_hours == 72


def test_recency_env_overrides_profile_default(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "usdjpy")
    monkeypatch.setenv("RECENCY_HOURS", "48")

    settings = get_settings()

    assert settings.recency_hours == 48


def test_usdjpy_exposes_summary_and_analysis_contracts():
    usdjpy = get_profile("usdjpy")
    assert usdjpy.resolve_summary_profile().narrative_field == "market_read"
    assert usdjpy.analysis_system_prompt
    assert usdjpy.source_entity_boost_rules == []
    assert usdjpy.cross_language_source_pairs == frozenset()
