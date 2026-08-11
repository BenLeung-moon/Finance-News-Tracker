from datetime import datetime, timezone

from finance_news_tracker.collectors.utils import (
    parse_date_from_text,
    parse_datetime_attr,
)
from finance_news_tracker.config import get_settings
from finance_news_tracker.models import Article
from finance_news_tracker.prefilter import prefilter_article


def test_parse_date_from_title():
    dt = parse_date_from_text("BOJ policy?Nov. 7, 2022")
    assert dt is not None
    assert dt.year == 2022


def test_parse_japanese_date():
    dt = parse_date_from_text("蓄電池プロジェクト 2026年3月25日 発表")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 25


def test_parse_numeric_date():
    dt = parse_date_from_text("Release 2026/03/25")
    assert dt is not None
    assert dt.month == 3


def test_parse_compact_yymmdd_date_from_url():
    dt = parse_date_from_text("https://www.tepco.co.jp/press/release/2026/pdf3/260709j0101.pdf")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 7
    assert dt.day == 9


def test_parse_datetime_attr_iso():
    dt = parse_datetime_attr("2026-03-25")
    assert dt is not None
    assert dt.year == 2026


def test_within_recency_rejects_missing_date():
    from finance_news_tracker.collectors.utils import within_recency

    assert within_recency(None, 72) is False


def test_enrich_published_at():
    from finance_news_tracker.collectors.utils import enrich_published_at

    a = Article(
        source="nhk_world",
        title="Japan GDP grows Nov. 7, 2022",
        url="https://example.com",
    )
    enrich_published_at(a)
    assert a.published_at is not None


def test_usdjpy_prefilter_hits_policy_keyword():
    settings = get_settings()
    article = Article(
        source="boj_whatsnew",
        title="BOJ keeps policy rate unchanged",
        url="https://example.com/1",
        published_at=datetime.now(timezone.utc),
    )
    hit, hits = prefilter_article(article, settings)
    assert hit is True
    assert hits
