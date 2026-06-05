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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_email_recipients(value: str) -> list[str]:
    """Parse comma-separated recipient addresses; empty entries are dropped."""
    return [part.strip() for part in value.split(",") if part.strip()]


@dataclass
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    data_dir: Path
    summaries_dir: Path
    log_dir: Path
    recency_hours: int
    min_relevance_score: int
    max_articles_to_score: int
    request_timeout_seconds: int
    user_agent: str
    # Scheduling / deployment
    run_timezone: str
    run_weekdays_only: bool
    holiday_guard_enabled: bool
    report_retention_days: int
    log_level: str
    # Email delivery (adapter layer; not used by run-once itself)
    email_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    email_from: str
    email_to: list[str]
    email_subject_prefix: str
    email_attach_docx: bool
    fx_keywords: list[str] = field(default_factory=lambda: list(FX_KEYWORDS))
    # Per-source caps for noisy FX media feeds (FXStreet, Investing.com)
    fx_media_score_limit_per_source: int = 3
    fx_media_score_limit_combined: int = 5
    dedupe_similarity_threshold: float = 0.82
    summary_max_per_source: int = 2

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tracker.db"

    @property
    def latest_report_manifest_path(self) -> Path:
        return self.summaries_dir / "latest_report.json"

    @property
    def run_lock_path(self) -> Path:
        return self.data_dir / "run.lock"


def get_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    summaries_dir = Path(os.getenv("SUMMARIES_DIR", "summaries"))
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    data_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        data_dir=data_dir,
        summaries_dir=summaries_dir,
        log_dir=log_dir,
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
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        user_agent=os.getenv(
            "USER_AGENT",
            "FinanceNewsTracker/0.1 (local research)",
        ),
        run_timezone=os.getenv("RUN_TIMEZONE", "Asia/Hong_Kong"),
        run_weekdays_only=_env_bool("RUN_WEEKDAYS_ONLY", True),
        holiday_guard_enabled=_env_bool("HOLIDAY_GUARD_ENABLED", False),
        report_retention_days=int(os.getenv("REPORT_RETENTION_DAYS", "90")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        email_enabled=_env_bool("EMAIL_ENABLED", False),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_use_tls=_env_bool("SMTP_USE_TLS", True),
        smtp_use_ssl=_env_bool("SMTP_USE_SSL", False),
        email_from=os.getenv("EMAIL_FROM", ""),
        email_to=parse_email_recipients(os.getenv("EMAIL_TO", "")),
        email_subject_prefix=os.getenv(
            "EMAIL_SUBJECT_PREFIX", "[Finance News Tracker]"
        ),
        email_attach_docx=_env_bool("EMAIL_ATTACH_DOCX", True),
    )
