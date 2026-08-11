from finance_news_tracker.config import get_settings
from finance_news_tracker.profiles import get_profile


def test_usdjpy_profile_has_nine_sources():
    profile = get_profile("usdjpy")
    assert len(profile.sources) == 9
    noisy = [s for s in profile.sources if s.is_noisy]
    assert len(noisy) == 2
    for source in profile.sources:
        assert source.kind in {"rss", "html"}
        assert source.languages


def test_settings_default_profile_is_usdjpy():
    settings = get_settings()
    assert settings.tracker_profile_id == "usdjpy"
    assert settings.active_profile.id == "usdjpy"
