from finance_news_tracker.config import get_settings
from finance_news_tracker.profiles import get_active_profile, get_profile, list_profiles
from finance_news_tracker.profiles.jp_storage import PROFILE as JP_STORAGE


def test_list_profiles():
    ids = list_profiles()
    assert "usdjpy" in ids
    assert "jp_storage" in ids


def test_get_profile_defaults_to_usdjpy():
    profile = get_profile()
    assert profile.id == "usdjpy"
    assert len(profile.sources) == 9


def test_get_profile_jp_storage():
    profile = get_profile("jp_storage")
    assert profile.id == "jp_storage"
    assert len(profile.sources) >= 30


def test_jp_storage_languages_are_en_or_ja_only():
    allowed = {"en", "ja"}
    for source in JP_STORAGE.sources:
        assert set(source.languages).issubset(allowed)
        assert source.languages


def test_settings_loads_active_profile():
    settings = get_settings()
    assert settings.active_profile.id == settings.tracker_profile_id
    assert settings.sources == settings.active_profile.sources


def test_jp_storage_has_policy_keywords():
    tiers = get_profile("jp_storage").keyword_tiers
    assert "容量市場" in tiers["policy"]
    assert "capacity market" in tiers["policy"]
