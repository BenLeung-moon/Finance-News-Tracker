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
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        user_agent=os.getenv(
            "USER_AGENT",
            "FinanceNewsTracker/0.1 (local research)",
        ),
    )
