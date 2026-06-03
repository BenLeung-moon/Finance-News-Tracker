from datetime import datetime, timezone

from finance_news_tracker.config import get_settings
from finance_news_tracker.models import Article
from finance_news_tracker.prefilter import prefilter_article, rank_for_scoring


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


def test_rank_limits_results():
    settings = get_settings()
    settings.max_articles_to_score = 2
    articles = [
        (
            Article(
                source="boj_whatsnew",
                title="Monetary Policy Statement",
                url=f"https://example.com/{i}",
                published_at=datetime.now(timezone.utc),
            ),
            i,
        )
        for i in range(5)
    ]
    ranked = rank_for_scoring(articles, settings)
    assert len(ranked) == 2
