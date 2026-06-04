from datetime import datetime, timezone

from finance_news_tracker.config import get_settings
from finance_news_tracker.dedupe import (
    articles_similar,
    dedupe_articles,
    diversify_scored_items,
    normalize_text,
    text_similarity,
)
from finance_news_tracker.models import Article
from finance_news_tracker.prefilter import prefilter_article, rank_for_scoring


def test_normalize_text_strips_boilerplate():
    assert "forex" not in normalize_text("FOREX: USD/JPY rises on Fed remarks")


def test_text_similarity_detects_near_duplicates():
    a = "USD/JPY climbs as Fed signals higher for longer"
    b = "USD/JPY climbs as the Fed signals higher for longer"
    assert text_similarity(a, b) >= 0.82


def test_articles_similar_cross_source():
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
    assert articles_similar(left, right, 0.82)


def test_dedupe_keeps_official_over_media():
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
    out = dedupe_articles(ranked, 0.82)
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
    settings.fx_media_score_limit_per_source = 2
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
    )
    assert len(diverse) == 2
