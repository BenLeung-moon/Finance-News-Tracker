from finance_news_tracker.checker import select_summary_items, topic_key
from finance_news_tracker.config import get_settings
from finance_news_tracker.sources import is_official_source


def _item(
    source: str,
    title: str,
    url: str,
    score: int,
    *,
    summary: str = "",
    fx_channel: str = "other",
) -> dict:
    return {
        "source": source,
        "title": title,
        "url": url,
        "relevance_score": score,
        "summary": summary,
        "why_it_matters": summary,
        "fx_channel": fx_channel,
        "likely_usdjpy_direction": "unclear",
        "confidence": "medium",
        "published_at": "2026-06-04T00:00:00+00:00",
    }


def test_topic_key_detects_intervention_theme():
    item = _item(
        "fxstreet_news",
        "Japanese Yen intervention risk rises near 160",
        "https://fxstreet.com/1",
        90,
        fx_channel="intervention",
    )
    assert topic_key(item) == "intervention_160"


def test_checker_reserves_official_sources():
    settings = get_settings()
    settings.checker_official_min = 2
    settings.summary_max_stories = 7
    settings.checker_intl_media_max_stories = 2

    candidates = [
        _item("fxstreet_news", f"USD/JPY media headline {i}", f"https://fx/{i}", 95 - i)
        for i in range(5)
    ] + [
        _item(
            "fed_press_monetary",
            "FOMC issues monetary policy statement",
            "https://fed.gov/1",
            88,
            fx_channel="monetary_policy",
        ),
        _item(
            "boj_whatsnew",
            "Statement on Monetary Policy at MPM",
            "https://boj.jp/1",
            85,
            fx_channel="monetary_policy",
        ),
        _item(
            "nhk_world",
            "BOJ chief hints at rate hike for June meeting",
            "https://nhk.jp/1",
            80,
            fx_channel="monetary_policy",
        ),
    ]

    stories, _ = select_summary_items(candidates, settings)
    official_count = sum(
        1 for item in stories if is_official_source(item["source"])
    )
    assert official_count >= 2


def test_checker_caps_international_media_stories():
    settings = get_settings()
    settings.checker_intl_media_max_stories = 2
    settings.summary_max_stories = 7
    settings.checker_official_min = 0

    candidates = [
        _item(
            "fxstreet_news",
            f"USD/JPY unique angle {i} on yen weakness",
            f"https://fxstreet.com/{i}",
            90 - i,
            summary=f"Theme {i} on carry trade and yields",
        )
        for i in range(6)
    ] + [
        _item(
            "investing_forex",
            "EUR/USD drifts lower in quiet session",
            "https://investing.com/eur",
            70,
        ),
    ]

    stories, _ = select_summary_items(candidates, settings)
    intl_count = sum(
        1
        for item in stories
        if item["source"] in {"fxstreet_news", "investing_forex"}
    )
    assert intl_count <= 2


def test_checker_collapses_repeated_intervention_media_topics():
    settings = get_settings()
    settings.checker_intl_media_max_stories = 2
    settings.summary_max_stories = 7
    settings.checker_official_min = 0

    candidates = [
        _item(
            "fxstreet_news",
            "Japanese Yen: Intervention risk rises near 160 against US Dollar",
            "https://fxstreet.com/a",
            92,
            fx_channel="intervention",
        ),
        _item(
            "investing_forex",
            "USD/JPY Near 160 Shows How Carry Trades Test Japan Patience",
            "https://investing.com/b",
            91,
            fx_channel="intervention",
        ),
        _item(
            "fxstreet_news",
            "Japanese Yen gains amid intervention threats near 160",
            "https://fxstreet.com/c",
            90,
            fx_channel="intervention",
        ),
        _item(
            "nikkei_asia",
            "Yen touches 160 against dollar, erasing intervention gains",
            "https://nikkei.com/d",
            89,
            fx_channel="intervention",
        ),
    ]

    stories, _ = select_summary_items(candidates, settings)
    intl_intervention = [
        item
        for item in stories
        if item["source"] in {"fxstreet_news", "investing_forex"}
        and topic_key(item) == "intervention_160"
    ]
    assert len(intl_intervention) <= 1


def test_checker_caps_international_media_citations():
    settings = get_settings()
    settings.checker_intl_media_max_citations = 3
    settings.summary_max_citations = 10
    settings.checker_official_min = 0

    candidates = [
        _item(
            "fxstreet_news",
            f"USD/JPY citation candidate {i}",
            f"https://fxstreet.com/cite{i}",
            80 - i,
            summary=f"Distinct macro angle {i} on payrolls and yields",
        )
        for i in range(6)
    ] + [
        _item(
            "fed_speeches",
            "Speech by Chair Powell on the economic outlook",
            "https://fed.gov/speech",
            75,
        ),
    ]

    _, citations = select_summary_items(candidates, settings)
    intl_count = sum(
        1
        for item in citations
        if item["source"] in {"fxstreet_news", "investing_forex"}
    )
    assert intl_count <= 3


def test_checker_does_not_force_unrelated_official_items():
    settings = get_settings()
    settings.checker_official_min = 2
    settings.summary_max_stories = 4
    settings.checker_intl_media_max_stories = 2
    settings.min_relevance_score = 60  # boj_statistics (45) should not be reserved

    candidates = [
        _item(
            "boj_statistics",
            "Flow of Funds for Q1 2026",
            "https://boj.jp/stats",
            45,
            summary="Quarterly balance sheet statistics release",
        ),
        _item(
            "fxstreet_news",
            "USD/JPY climbs on US payrolls beat",
            "https://fxstreet.com/payrolls",
            90,
            summary="Labor data widens US-Japan rate differential",
        ),
        _item(
            "investing_forex",
            "USD/JPY compression near 160 sets up June policy test",
            "https://investing.com/160",
            88,
            summary="Binary policy test for yen crosses",
        ),
        _item(
            "nhk_world",
            "BOJ chief hints at rate hike for June meeting",
            "https://nhk.jp/boj",
            86,
            summary="Rate hike would narrow differential",
        ),
        _item(
            "nikkei_asia",
            "Yen touches 160 against dollar",
            "https://nikkei.com/yen",
            84,
            summary="Intervention risk rises at key level",
        ),
        _item(
            "fed_speeches",
            "Speech by Chair Powell on the economic outlook",
            "https://fed.gov/speech",
            82,
            summary="Fed guidance shapes rate differential",
        ),
    ]

    stories, _ = select_summary_items(candidates, settings)
    sources = {item["source"] for item in stories}
    assert "boj_statistics" not in sources
    assert len(stories) == 4
    assert is_official_source(next(s for s in sources if s == "fed_speeches"))
