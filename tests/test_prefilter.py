from datetime import datetime, timezone

from finance_news_tracker.config import get_settings
from finance_news_tracker.models import Article
from finance_news_tracker.prefilter import (
    _source_entity_boost,
    prefilter_article,
    rank_for_scoring,
)


def test_prefilter_hits_fx_keyword():
    settings = get_settings()
    article = Article(
        source="nikkei_asia",
        title="BOJ holds rates steady as yen weakens",
        url="https://example.com/1",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True
    assert len(hits) > 0


def test_boj_macro_fallback():
    settings = get_settings()
    article = Article(
        source="boj_whatsnew",
        title="Statement on Monetary Policy",
        url="https://www.boj.or.jp/en/example",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True


def test_fed_macro_fallback():
    settings = get_settings()
    article = Article(
        source="fed_speeches",
        title="Speech by Chair Powell on the economic outlook",
        url="https://www.federalreserve.gov/example",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True
    assert "fed_macro" in hits or "powell" in hits


def test_us_treasury_macro_fallback():
    settings = get_settings()
    article = Article(
        source="us_treasury_press",
        title="Treasury International Capital Data for March",
        url="https://home.treasury.gov/example",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True


def test_rank_prioritizes_official_over_media():
    settings = get_settings()
    settings.max_articles_to_score = 10
    now = datetime.now(timezone.utc)
    articles = [
        (
            Article(
                source="fxstreet_news",
                title="USD/JPY steady as celebrity home sales slump in LA",
                url="https://fxstreet.com/low-signal",
                published_at=now,
            ),
            1,
        ),
        (
            Article(
                source="fed_press_monetary",
                title="FOMC issues monetary policy statement",
                url="https://federalreserve.gov/fomc",
                published_at=now,
            ),
            2,
        ),
    ]
    ranked = rank_for_scoring(articles, settings)
    assert ranked[0][0].source.startswith("fed_")


def test_media_generic_headline_excluded_from_rank():
    settings = get_settings()
    settings.max_articles_to_score = 10
    now = datetime.now(timezone.utc)
    articles = [
        (
            Article(
                source="investing_forex",
                title="Forex today: majors mixed in quiet session",
                url="https://investing.com/generic",
                published_at=now,
            ),
            1,
        ),
        (
            Article(
                source="boj_whatsnew",
                title="Statement on Monetary Policy",
                url="https://www.boj.or.jp/en/example",
                published_at=now,
            ),
            2,
        ),
    ]
    ranked = rank_for_scoring(articles, settings)
    sources = {a.source for a, _ in ranked}
    assert "investing_forex" not in sources
    assert "boj_whatsnew" in sources


def test_rank_limits_results():
    settings = get_settings()
    settings.max_articles_to_score = 2
    titles = [
        "Statement on Monetary Policy at MPM",
        "Tankan quarterly survey released",
        "BOJ purchases JGBs under outright program",
        "Summary of opinions at January MPM",
        "Outlook for economic activity and prices",
    ]
    articles = [
        (
            Article(
                source="boj_whatsnew",
                title=titles[i],
                url=f"https://example.com/{i}",
                published_at=datetime.now(timezone.utc),
            ),
            i,
        )
        for i in range(5)
    ]
    ranked = rank_for_scoring(articles, settings)
    assert len(ranked) == 2


def test_jp_storage_tokyo_gas_tolling_english(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    article = Article(
        source="japan_energy_hub",
        title="Tokyo Gas signs a tolling agreement for grid storage",
        url="https://example.com/tokyo-gas-tolling",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True
    assert "Tokyo Gas" in hits
    assert "tolling agreement" in hits


def test_jp_storage_tokyo_gas_tolling_japanese(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    article = Article(
        source="enehub_jp",
        title="東京ガスがトーリング契約を締結",
        url="https://example.com/tokyo-gas-ja",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True
    assert "東京ガス" in hits
    assert "トーリング契約" in hits


def test_jeh_epc_bonus_entity_only(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    article = Article(
        source="japan_energy_hub",
        title="TESS Engineering announces corporate restructuring",
        url="https://example.com/tess-only",
        published_at=datetime.now(timezone.utc),
    )
    bonus, signals = _source_entity_boost(article, settings)
    assert bonus == 1
    assert "epc:TESS Engineering" in signals
    assert not any(s.startswith("epc_context:") for s in signals)


def test_jeh_epc_bonus_with_context(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    article = Article(
        source="japan_energy_hub",
        title="TESS Engineering wins battery storage EPC contract",
        url="https://example.com/tess-bess",
        published_at=datetime.now(timezone.utc),
    )
    bonus, signals = _source_entity_boost(article, settings)
    assert bonus == 2
    assert "epc:TESS Engineering" in signals
    assert any(s.startswith("epc_context:") for s in signals)


def test_epc_bonus_other_source_zero(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    article = Article(
        source="enehub_jp",
        title="TESS Engineering wins battery storage EPC contract",
        url="https://example.com/tess-other-source",
        published_at=datetime.now(timezone.utc),
    )
    bonus, signals = _source_entity_boost(article, settings)
    assert bonus == 0
    assert signals == []


def test_jeh_unknown_company_no_bonus(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    article = Article(
        source="japan_energy_hub",
        title="Acme Corp announces battery storage project in Japan",
        url="https://example.com/unknown-co",
        published_at=datetime.now(timezone.utc),
    )
    bonus, signals = _source_entity_boost(article, settings)
    assert bonus == 0
    assert signals == []


def test_jeh_kajima_building_news_entity_only(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "jp_storage")
    settings = get_settings()
    article = Article(
        source="japan_energy_hub",
        title="Kajima completes downtown office tower renovation",
        url="https://example.com/kajima-building",
        published_at=datetime.now(timezone.utc),
    )
    bonus, signals = _source_entity_boost(article, settings)
    assert bonus == 1
    assert "epc:Kajima" in signals
    assert not any(s.startswith("epc_context:") for s in signals)


def test_usdjpy_no_jp_storage_epc_boost(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "usdjpy")
    settings = get_settings()
    article = Article(
        source="japan_energy_hub",
        title="Tokyo Gas and TESS Engineering battery storage EPC",
        url="https://example.com/usdjpy-no-boost",
        published_at=datetime.now(timezone.utc),
    )
    bonus, signals = _source_entity_boost(article, settings)
    assert bonus == 0
    assert signals == []
    assert settings.active_profile.source_entity_boost_rules == []
