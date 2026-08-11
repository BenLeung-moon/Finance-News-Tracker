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


def test_usdjpy_source_entity_boost_rules_empty(monkeypatch):
    monkeypatch.setenv("TRACKER_PROFILE", "usdjpy")
    settings = get_settings()
    article = Article(
        source="fxstreet_news",
        title="Acme Corp announces battery storage EPC",
        url="https://example.com/no-boost",
        published_at=datetime.now(timezone.utc),
    )
    bonus, signals = _source_entity_boost(article, settings)
    assert bonus == 0
    assert signals == []
    assert settings.active_profile.source_entity_boost_rules == []


def test_source_entity_boost_applies_configured_rule(monkeypatch):
    """Framework hook: profile-supplied rules boost ranking without prefilter pass."""
    from finance_news_tracker.profiles.base import SourceEntityBoostRule

    monkeypatch.setenv("TRACKER_PROFILE", "usdjpy")
    settings = get_settings()
    previous = settings.active_profile.source_entity_boost_rules
    settings.active_profile.source_entity_boost_rules = [
        SourceEntityBoostRule(
            source_id="fxstreet_news",
            entity_aliases={"Acme Corp": ["Acme Corp", "Acme"]},
            context_keywords=["battery storage"],
            entity_bonus=1,
            context_bonus=1,
            max_bonus=2,
        )
    ]
    try:
        article = Article(
            source="fxstreet_news",
            title="Acme Corp wins battery storage contract",
            url="https://example.com/boost",
            published_at=datetime.now(timezone.utc),
        )
        bonus, signals = _source_entity_boost(article, settings)
        assert bonus == 2
        assert "entity:Acme Corp" in signals
        assert any(s.startswith("entity_context:") for s in signals)
    finally:
        settings.active_profile.source_entity_boost_rules = previous
