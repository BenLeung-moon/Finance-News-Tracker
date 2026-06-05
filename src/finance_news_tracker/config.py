from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# USD/JPY relevance prefilter keywords
FX_KEYWORDS: list[str] = [
    "usd/jpy",
    "usd-jpy",
    "dollar-yen",
    "dollar yen",
    "usdjpy",
    "yen",
    "jpy",
    "boj",
    "bank of japan",
    "fed",
    "federal reserve",
    "rate",
    "rates",
    "interest rate",
    "monetary policy",
    "inflation",
    "cpi",
    "wage",
    "wages",
    "jgb",
    "bond",
    "treasury",
    "yield",
    "intervention",
    "mof",
    "finance ministry",
    "trade balance",
    "current account",
    "oil",
    "crude",
    "risk-off",
    "risk on",
    "carry trade",
    "fx",
    "forex",
    "exchange rate",
    "currency",
    "dollar",
    "gdp",
    "pmi",
    "tankan",
    "mpm",
    "statement on monetary policy",
    "fomc",
    "powell",
    "fed funds",
    "treasury yields",
    "tic",
    "treasury international capital",
    "quarterly refunding",
    "payrolls",
    "pce",
    "ppi",
    "retail sales",
    "ism",
    "tariff",
    "debt issuance",
    "fiscal",
]


@dataclass
class SourceConfig:
    id: str
    name: str
    kind: str  # "rss" | "html"
    url: str
    extra_urls: list[str] = field(default_factory=list)


SOURCES: list[SourceConfig] = [
    SourceConfig(
        id="boj_whatsnew",
        name="Bank of Japan (What's New)",
        kind="rss",
        # English feed: titles come through in English (the non-/en/ feed is Japanese)
        url="https://www.boj.or.jp/en/rss/whatsnew.xml",
    ),
    SourceConfig(
        id="boj_statistics",
        name="Bank of Japan (Statistics)",
        kind="rss",
        url="https://www.boj.or.jp/en/rss/statistics.xml",
    ),
    SourceConfig(
        id="nikkei_asia",
        name="Nikkei Asia",
        kind="rss",
        url="https://asia.nikkei.com/rss/feed/nar",
    ),
    SourceConfig(
        id="nhk_world",
        name="NHK WORLD-JAPAN",
        kind="html",
        url="https://www3.nhk.or.jp/nhkworld/en/news/list/",
        extra_urls=[
            "https://www3.nhk.or.jp/nhkworld/en/news/tags/60/",  # Biz / Tech
            "https://www3.nhk.or.jp/nhkworld/en/news/",
        ],
    ),
    SourceConfig(
        id="fed_press_monetary",
        name="Federal Reserve (Monetary Policy Press)",
        kind="rss",
        url="https://www.federalreserve.gov/feeds/press_monetary.xml",
    ),
    SourceConfig(
        id="fed_speeches",
        name="Federal Reserve (Speeches)",
        kind="rss",
        url="https://www.federalreserve.gov/feeds/speeches.xml",
    ),
    SourceConfig(
        id="us_treasury_press",
        name="US Treasury (Press Releases)",
        kind="html",
        url="https://home.treasury.gov/news/press-releases",
    ),
    SourceConfig(
        id="fxstreet_news",
        name="FXStreet (Forex News)",
        kind="rss",
        url="https://www.fxstreet.com/rss/news",
    ),
    SourceConfig(
        id="investing_forex",
        name="Investing.com (Forex)",
        kind="rss",
        url="https://www.investing.com/rss/forex.rss",
    ),
]


@dataclass
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    data_dir: Path
    recency_hours: int
    min_relevance_score: int
    max_articles_to_score: int
    request_timeout_seconds: int
    user_agent: str
    fx_keywords: list[str] = field(default_factory=lambda: list(FX_KEYWORDS))
    # Per-source caps for noisy FX media feeds (FXStreet, Investing.com)
    fx_media_score_limit_per_source: int = 3
    fx_media_score_limit_combined: int = 5
    dedupe_similarity_threshold: float = 0.82
    summary_max_per_source: int = 2
    # Checker: wider candidate pool + category quotas for final selection
    summary_candidate_pool_limit: int = 50
    summary_max_stories: int = 7
    summary_max_citations: int = 15
    checker_official_min: int = 2
    checker_intl_media_max_stories: int = 2
    checker_local_media_max_stories: int = 3
    checker_intl_media_max_citations: int = 3

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tracker.db"

    @property
    def summaries_dir(self) -> Path:
        return Path("summaries")


def get_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        data_dir=data_dir,
        recency_hours=int(os.getenv("RECENCY_HOURS", "72")),
        min_relevance_score=int(os.getenv("MIN_RELEVANCE_SCORE", "40")),
        max_articles_to_score=int(os.getenv("MAX_ARTICLES_TO_SCORE", "25")),
        fx_media_score_limit_per_source=int(
            os.getenv("FX_MEDIA_SCORE_LIMIT_PER_SOURCE", "3")
        ),
        fx_media_score_limit_combined=int(
            os.getenv("FX_MEDIA_SCORE_LIMIT_COMBINED", "5")
        ),
        dedupe_similarity_threshold=float(
            os.getenv("DEDUPE_SIMILARITY_THRESHOLD", "0.82")
        ),
        summary_max_per_source=int(os.getenv("SUMMARY_MAX_PER_SOURCE", "2")),
        summary_candidate_pool_limit=int(
            os.getenv("SUMMARY_CANDIDATE_POOL_LIMIT", "50")
        ),
        summary_max_stories=int(os.getenv("SUMMARY_MAX_STORIES", "7")),
        summary_max_citations=int(os.getenv("SUMMARY_MAX_CITATIONS", "15")),
        checker_official_min=int(os.getenv("CHECKER_OFFICIAL_MIN", "2")),
        checker_intl_media_max_stories=int(
            os.getenv("CHECKER_INTL_MEDIA_MAX_STORIES", "2")
        ),
        checker_local_media_max_stories=int(
            os.getenv("CHECKER_LOCAL_MEDIA_MAX_STORIES", "3")
        ),
        checker_intl_media_max_citations=int(
            os.getenv("CHECKER_INTL_MEDIA_MAX_CITATIONS", "3")
        ),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        user_agent=os.getenv(
            "USER_AGENT",
            "FinanceNewsTracker/0.1 (local research)",
        ),
    )
