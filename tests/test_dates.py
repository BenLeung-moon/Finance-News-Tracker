from datetime import datetime, timezone

from finance_news_tracker.collectors.utils import (
    parse_date_from_text,
    within_recency,
)
from finance_news_tracker.models import Article
from finance_news_tracker.collectors.utils import enrich_published_at


def test_parse_date_from_title():
    dt = parse_date_from_text("BOJ policy?Nov. 7, 2022")
    assert dt is not None
    assert dt.year == 2022


def test_within_recency_rejects_missing_date():
    assert within_recency(None, 72) is False


def test_enrich_published_at():
    a = Article(
        source="nhk_world",
        title="Japan GDP grows Nov. 7, 2022",
        url="https://example.com",
    )
    enrich_published_at(a)
    assert a.published_at is not None
