from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from finance_news_tracker.profiles import get_active_profile, get_profile
from finance_news_tracker.profiles.base import SourceConfig, TrackerProfile

load_dotenv()


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
    llm_provider: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    anthropic_api_key: str
    anthropic_base_url: str
    anthropic_model: str
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
    tracker_profile_id: str
    active_profile: TrackerProfile
    # Per-source caps for noisy feeds (FXStreet, Investing.com, etc.)
    noisy_score_limit_per_source: int = 3
    noisy_score_limit_combined: int = 5
    dedupe_similarity_threshold: float = 0.82
    summary_max_per_source: int = 2

    @property
    def sources(self) -> list[SourceConfig]:
        return self.active_profile.sources

    @property
    def keywords(self) -> list[str]:
        return self.active_profile.flat_keywords()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tracker.db"

    @property
    def latest_report_manifest_path(self) -> Path:
        return self.summaries_dir / "latest_report.json"

    @property
    def run_lock_path(self) -> Path:
        return self.data_dir / "run.lock"

    def resolve_llm_config(
        self,
        provider: str | None = None,
        model: str | None = None,
    ):
        """Resolve None to the configured active provider, never to all providers.

        中文注解：`provider=None` 只代表当前默认 provider，不能代表全表混合查询。
        """
        from finance_news_tracker.llm import LlmConfig

        selected_provider = (provider or self.llm_provider).strip().lower()
        if selected_provider == "deepseek":
            return LlmConfig(
                provider="deepseek",
                model=model or self.deepseek_model,
                api_key=self.deepseek_api_key,
                base_url=self.deepseek_base_url,
            )
        if selected_provider == "openai":
            return LlmConfig(
                provider="openai",
                model=model or self.openai_model,
                api_key=self.openai_api_key,
                base_url=self.openai_base_url,
            )
        if selected_provider == "anthropic":
            return LlmConfig(
                provider="anthropic",
                model=model or self.anthropic_model,
                api_key=self.anthropic_api_key,
                base_url=self.anthropic_base_url,
            )
        raise ValueError(
            "Unsupported LLM_PROVIDER. Expected one of: deepseek, openai, anthropic."
        )


def get_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    summaries_dir = Path(os.getenv("SUMMARIES_DIR", "summaries"))
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    data_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    profile_id = os.getenv("TRACKER_PROFILE", "usdjpy").strip().lower()
    active_profile = get_profile(profile_id)

    # Accept legacy FX_MEDIA_* env names for backward compatibility
    noisy_per_source = int(
        os.getenv(
            "NOISY_SCORE_LIMIT_PER_SOURCE",
            os.getenv("FX_MEDIA_SCORE_LIMIT_PER_SOURCE", "3"),
        )
    )
    noisy_combined = int(
        os.getenv(
            "NOISY_SCORE_LIMIT_COMBINED",
            os.getenv("FX_MEDIA_SCORE_LIMIT_COMBINED", "5"),
        )
    )

    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "deepseek"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        ),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_base_url=os.getenv(
            "ANTHROPIC_BASE_URL",
            "https://api.anthropic.com/v1",
        ),
        anthropic_model=os.getenv(
            "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
        ),
        data_dir=data_dir,
        summaries_dir=summaries_dir,
        log_dir=log_dir,
        recency_hours=int(os.getenv("RECENCY_HOURS", "72")),
        min_relevance_score=int(os.getenv("MIN_RELEVANCE_SCORE", "40")),
        max_articles_to_score=int(os.getenv("MAX_ARTICLES_TO_SCORE", "25")),
        noisy_score_limit_per_source=noisy_per_source,
        noisy_score_limit_combined=noisy_combined,
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
        tracker_profile_id=profile_id,
        active_profile=active_profile,
    )


# Backward-compatible module-level aliases (default profile)
_default = get_active_profile()
SOURCES: list[SourceConfig] = _default.sources
FX_KEYWORDS: list[str] = _default.flat_keywords()
