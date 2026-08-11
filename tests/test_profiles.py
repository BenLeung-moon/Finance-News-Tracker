from finance_news_tracker.config import get_settings
from finance_news_tracker.profiles import get_profile, list_profiles
from finance_news_tracker.profiles.jp_storage import (
    PROFILE as JP_STORAGE,
    SOURCE_LABELS,
    _JEH_EPC_ENTITIES,
)


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


def test_blank_recency_env_uses_profile_default(monkeypatch):
    """An explicitly blank .env value must not override the profile default.

    中文注解：RECENCY_HOURS=（空值）应使用当前 Profile 的默认回看窗口。
    """
    monkeypatch.setenv("RECENCY_HOURS", "")
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


def test_jp_storage_battery_supplier_sources():
    sources = get_profile("jp_storage").source_by_id()
    source_ids = [s.id for s in get_profile("jp_storage").sources]
    assert len(source_ids) == len(set(source_ids))

    catl = sources["catl_news"]
    assert catl.url == "https://www.catl.com/en/news/"
    assert catl.priority_tier == 2
    assert catl.languages == ["en"]
    assert "/en/news/" in catl.link_patterns
    assert "index_" in catl.exclude_patterns
    assert catl.title_selector == "p.mc_e1_txt"
    assert catl.date_selector == "div.mc_e1_date"

    byd = sources["byd_energy_news"]
    assert byd.kind == "byd_energy"
    assert byd.url == "https://cms-api.byd.com/es/search"
    assert byd.priority_tier == 2
    assert byd.languages == ["en"]

    hithium = sources["hithium_latest_updates"]
    assert hithium.url == "https://www.hithium.com/newsroom/LatestUpdates"
    assert hithium.priority_tier == 2
    assert hithium.languages == ["en"]
    assert "/newsroom/latest/details/" in hithium.link_patterns
    assert hithium.title_selector == "h1"
    assert hithium.date_selector == "div.time"

    for sid in ("catl_news", "byd_energy_news", "hithium_latest_updates"):
        assert sid in SOURCE_LABELS


def test_jp_storage_tolling_and_tokyo_gas_keywords():
    tiers = get_profile("jp_storage").keyword_tiers
    assert "tolling agreement" in tiers["company"]
    assert "トーリング契約" in tiers["company"]
    assert "Tokyo Gas" in tiers["entity"]
    assert "東京ガス" in tiers["entity"]
    assert "Tokyo Gas" in tiers["general"]
    assert "tolling agreement" in tiers["general"]


def test_jp_storage_epc_not_in_global_keywords():
    tiers = get_profile("jp_storage").keyword_tiers
    epc_aliases = [
        alias
        for aliases in _JEH_EPC_ENTITIES.values()
        for alias in aliases
    ]
    for bucket in ("general", "company", "entity", "policy", "project"):
        for alias in epc_aliases:
            assert alias not in tiers[bucket]

    rules = get_profile("jp_storage").source_entity_boost_rules
    assert len(rules) == 1
    assert rules[0].source_id == "japan_energy_hub"
    assert rules[0].max_bonus == 2
