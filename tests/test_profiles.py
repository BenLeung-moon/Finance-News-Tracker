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
    assert profile.default_recency_hours == 14 * 24


def test_jp_storage_languages_are_en_or_ja_only():
    allowed = {"en", "ja"}
    for source in JP_STORAGE.sources:
        assert set(source.languages).issubset(allowed)
        assert source.languages


def test_settings_loads_active_profile():
    settings = get_settings()
    assert settings.active_profile.id == settings.tracker_profile_id
    assert settings.sources == settings.active_profile.sources


def test_settings_uses_profile_recency_default(monkeypatch):
    monkeypatch.delenv("RECENCY_HOURS", raising=False)
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")

    settings = get_settings()

    assert settings.recency_hours == 14 * 24


def test_recency_env_overrides_profile_default(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    monkeypatch.setenv("RECENCY_HOURS", "48")

    settings = get_settings()

    assert settings.recency_hours == 48


def test_jp_storage_has_policy_keywords():
    tiers = get_profile("jp_storage").keyword_tiers
    assert "容量市場" in tiers["policy"]
    assert "capacity market" in tiers["policy"]


def test_jp_storage_uses_planned_source_fallbacks():
    sources = get_profile("jp_storage").source_by_id()
    assert sources["occto_rss"].kind == "rss"
    assert sources["occto_news"].url == "https://www.occto.or.jp/"
    assert sources["itochu_press"].kind == "rss"
    assert sources["panasonic_energy_news"].kind == "rss"
    assert sources["sumitomo_release"].kind == "sumitomo_archive"
    assert sources["sumitomo_topics"].kind == "sumitomo_archive"
    assert "www.hitachi.co.jp" in sources["hitachi_power_solutions_press"].allowed_domains
    assert sources["anre_news_release"].url == "https://www.meti.go.jp/press/category_05.html"
    assert sources["enehub_jp"].kind == "enehub"
    assert sources["enehub_jp"].languages == ["ja"]
    assert sources["japan_energy_hub"].kind == "rss"
    assert sources["japan_energy_hub"].url == (
        "https://japanenergyhub.com/feed/?post_type=news"
    )
    assert sources["japan_energy_hub"].languages == ["en"]
    assert sources["japan_energy_hub"].prefer_feed_content


def test_profiles_expose_summary_and_analysis_contracts():
    usdjpy = get_profile("usdjpy")
    jp = get_profile("jp_storage")
    assert usdjpy.resolve_summary_profile().narrative_field == "market_read"
    assert jp.summary_profile is not None
    assert "policy" in jp.analysis_schema.category_options
    assert usdjpy.analysis_system_prompt
    assert jp.analysis_system_prompt
