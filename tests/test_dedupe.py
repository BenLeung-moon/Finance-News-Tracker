from datetime import datetime, timezone

from finance_news_tracker.config import get_settings
from finance_news_tracker.dedupe import (
    articles_similar,
    cross_language_articles_similar,
    dedupe_articles,
    diversify_scored_items,
    normalize_text,
    text_similarity,
)
from finance_news_tracker.models import Article
from finance_news_tracker.prefilter import prefilter_article, rank_for_scoring


def test_normalize_text_strips_boilerplate():
    settings = get_settings()
    assert "forex" not in normalize_text("FOREX: USD/JPY rises on Fed remarks", settings)


def test_text_similarity_detects_near_duplicates():
    settings = get_settings()
    a = "USD/JPY climbs as Fed signals higher for longer"
    b = "USD/JPY climbs as the Fed signals higher for longer"
    assert text_similarity(a, b, settings) >= 0.82


def test_articles_similar_cross_source():
    settings = get_settings()
    left = Article(
        source="fxstreet_news",
        title="USD/JPY rises after BOJ holds rates",
        url="https://fxstreet.com/1",
    )
    right = Article(
        source="investing_forex",
        title="USD/JPY rises after BOJ holds rates",
        url="https://investing.com/1",
    )
    assert articles_similar(left, right, 0.82, settings)


def _with_cross_language_pairs(settings, pairs: frozenset[frozenset[str]]):
    """Temporarily set profile pairs; restores previous value via caller.

    中文注解：临时改写共享 PROFILE 字段前先返回旧值，避免污染其他测试。
    """
    profile = settings.active_profile
    previous = profile.cross_language_source_pairs
    profile.cross_language_source_pairs = pairs
    return previous


def test_cross_language_dedupe_matches_shared_entity_and_capacity():
    """Profile-configured source pairs enable fact-based cross-language match."""
    settings = get_settings()
    previous = _with_cross_language_pairs(
        settings, frozenset({frozenset({"source_en", "source_ja"})})
    )
    try:
        published = datetime(2026, 7, 6, tzinfo=timezone.utc)
        english = Article(
            source="source_en",
            title=(
                "IBeeT, Tokyu Land, Akaysha begin construction "
                "of 20MW/82MWh Fukuoka BESS project"
            ),
            url="https://example.com/en/ibeet-fukuoka-bess/",
            published_at=published,
        )
        japanese = Article(
            source="source_ja",
            title="IBeeT・東急不動産・Akaysha、福岡県飯塚市で20MW/82MWh蓄電所を着工",
            url="https://example.com/ja/ibeet-fukuoka-bess/",
            published_at=published,
        )

        assert cross_language_articles_similar(english, japanese, settings)
        assert articles_similar(english, japanese, 0.82, settings)
    finally:
        settings.active_profile.cross_language_source_pairs = previous


def test_cross_language_dedupe_off_when_pairs_empty():
    settings = get_settings()
    previous = _with_cross_language_pairs(settings, frozenset())
    try:
        published = datetime(2026, 7, 6, tzinfo=timezone.utc)
        english = Article(
            source="source_en",
            title="IBeeT and Akaysha begin 20MW/82MWh Fukuoka project",
            url="https://example.com/en/a/",
            published_at=published,
        )
        japanese = Article(
            source="source_ja",
            title="IBeeT・Akaysha、福岡で20MW/82MWh蓄電所を着工",
            url="https://example.com/ja/a/",
            published_at=published,
        )
        assert not cross_language_articles_similar(english, japanese, settings)
    finally:
        settings.active_profile.cross_language_source_pairs = previous


def test_cross_language_dedupe_rejects_generic_or_distant_matches():
    settings = get_settings()
    previous = _with_cross_language_pairs(
        settings, frozenset({frozenset({"source_en", "source_ja"})})
    )
    try:
        english = Article(
            source="source_en",
            title="A developer begins 20MW battery storage construction",
            url="https://example.com/en/a/",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )
        unrelated = Article(
            source="source_ja",
            title="別事業者、北海道で20MW蓄電所の建設を開始",
            url="https://example.com/ja/b/",
            published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        distant = Article(
            source="source_ja",
            title="Akaysha、福岡県で20MW/82MWh蓄電所を着工",
            url="https://example.com/ja/c/",
            published_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
        )
        matching_english = Article(
            source="source_en",
            title="Akaysha begins 20MW/82MWh Fukuoka battery project",
            url="https://example.com/en/d/",
            published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

        assert not cross_language_articles_similar(english, unrelated, settings)
        assert not cross_language_articles_similar(matching_english, distant, settings)
        assert not articles_similar(english, unrelated, 0.82, settings)
    finally:
        settings.active_profile.cross_language_source_pairs = previous


def test_cross_language_dedupe_decodes_html_entities_in_identifiers():
    settings = get_settings()
    previous = _with_cross_language_pairs(
        settings, frozenset({frozenset({"source_en", "source_ja"})})
    )
    try:
        published = datetime(2026, 7, 14, tzinfo=timezone.utc)
        english = Article(
            source="source_en",
            title="au Renewable Energy considers ORIX grid-scale battery O&amp;M",
            url="https://example.com/en/au-orix/",
            published_at=published,
        )
        japanese = Article(
            source="source_ja",
            title="au、ORIX子会社に蓄電所のO&M委託を検討",
            url="https://example.com/ja/au-orix/",
            published_at=published,
        )

        assert cross_language_articles_similar(english, japanese, settings)
    finally:
        settings.active_profile.cross_language_source_pairs = previous


def test_dedupe_keeps_official_over_media():
    settings = get_settings()
    now = datetime.now(timezone.utc)
    fed = Article(
        source="fed_press_monetary",
        title="FOMC holds rates; USD/JPY volatile",
        url="https://fed.gov/1",
        published_at=now,
    )
    fx = Article(
        source="fxstreet_news",
        title="FOMC holds rates USD/JPY volatile",
        url="https://fxstreet.com/1",
        published_at=now,
    )
    ranked = [(fx, 1, 5), (fed, 2, 8)]
    out = dedupe_articles(ranked, 0.82, settings)
    sources = {a.source for a, _, _ in out}
    assert "fed_press_monetary" in sources
    assert len(out) == 1


def test_media_prefilter_rejects_generic_forex():
    settings = get_settings()
    article = Article(
        source="fxstreet_news",
        title="Forex today: mixed moves in major currencies",
        url="https://fxstreet.com/generic",
        published_at=datetime.now(timezone.utc),
    )
    hit, _ = prefilter_article(article, settings)
    assert hit is False


def test_media_prefilter_accepts_direct_usdjpy():
    settings = get_settings()
    article = Article(
        source="investing_forex",
        title="USD/JPY hits multi-week high on yield gap",
        url="https://investing.com/usdjpy",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True
    assert any("usd" in h.lower() or "jpy" in h.lower() or "yen" in h.lower() for h in hits)


def test_rank_applies_media_source_quota():
    settings = get_settings()
    settings.max_articles_to_score = 10
    settings.noisy_score_limit_per_source = 2
    now = datetime.now(timezone.utc)
    articles = []
    for i in range(5):
        articles.append(
            (
                Article(
                    source="fxstreet_news",
                    title=f"USD/JPY outlook update {i} unique headline {i}",
                    url=f"https://fxstreet.com/{i}",
                    published_at=now,
                    summary=f"Yen moves on BOJ and Fed theme {i}",
                ),
                i + 1,
            )
        )
    ranked = rank_for_scoring(articles, settings)
    fx_count = sum(1 for a, _ in ranked if a.source == "fxstreet_news")
    assert fx_count <= 2


def test_rank_dedupes_similar_media_headlines():
    settings = get_settings()
    settings.max_articles_to_score = 10
    now = datetime.now(timezone.utc)
    articles = [
        (
            Article(
                source="fxstreet_news",
                title="USD/JPY rises as US yields climb",
                url="https://fxstreet.com/a",
                published_at=now,
            ),
            1,
        ),
        (
            Article(
                source="investing_forex",
                title="USD/JPY rises as US yields climb",
                url="https://investing.com/b",
                published_at=now,
            ),
            2,
        ),
    ]
    ranked = rank_for_scoring(articles, settings)
    assert len(ranked) == 1


def test_diversify_scored_items_caps_per_source():
    settings = get_settings()
    settings.summary_max_per_source = 2
    items = [
        {
            "source": "fxstreet_news",
            "title": "USD/JPY jumps after strong US payrolls beat",
            "url": "https://fxstreet.com/payrolls",
            "relevance_score": 90,
            "summary": "Labor data widens rate differential versus Japan",
        },
        {
            "source": "fxstreet_news",
            "title": "Japan MOF official warns on excessive yen weakness",
            "url": "https://fxstreet.com/intervention",
            "relevance_score": 85,
            "summary": "Intervention rhetoric lifts yen briefly",
        },
        {
            "source": "fxstreet_news",
            "title": "JGB auction tail signals higher long-end yields",
            "url": "https://fxstreet.com/jgb",
            "relevance_score": 80,
            "summary": "Domestic bond supply weighs on yen crosses",
        },
        {
            "source": "fxstreet_news",
            "title": "Oil spike raises Japan import bill, yen under pressure",
            "url": "https://fxstreet.com/oil",
            "relevance_score": 75,
            "summary": "Energy terms-of-trade shock for yen",
        },
    ]
    diverse = diversify_scored_items(
        items,
        max_items=12,
        max_per_source=2,
        threshold=settings.dedupe_similarity_threshold,
        settings=settings,
    )
    assert len(diverse) == 2
