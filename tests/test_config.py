from finance_news_tracker.config import get_settings
from finance_news_tracker.profiles import get_profile


def test_jp_storage_source_domains():
    profile = get_profile("jp_storage")
    domains = set()
    for source in profile.sources:
        assert source.kind in {"enehub", "html", "rss", "sumitomo_archive", "byd_energy"}
        assert source.languages
        for lang in source.languages:
            assert lang in {"en", "ja"}
        if source.url_year_templated:
            assert "{year}" in source.url
        domains.add(source.url.split("/")[2])
    assert "www.meti.go.jp" in domains
    assert "www.jera-cross.com" in domains
    assert "enehub.jp" in domains
    assert "japanenergyhub.com" in domains
    assert "www.catl.com" in domains
    assert "cms-api.byd.com" in domains
    assert "www.hithium.com" in domains


def test_usdjpy_profile_has_nine_sources():
    profile = get_profile("usdjpy")
    assert len(profile.sources) == 9
    noisy = [s for s in profile.sources if s.is_noisy]
    assert len(noisy) == 2
