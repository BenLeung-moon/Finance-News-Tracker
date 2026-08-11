"""Shared test fixtures for Settings construction."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from finance_news_tracker.config import Settings, get_settings
from finance_news_tracker.profiles import get_profile


@pytest.fixture(autouse=True)
def _default_usdjpy_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests assume USD/JPY unless they override TRACKER_PROFILE explicitly."""
    monkeypatch.setenv("TRACKER_PROFILE", "usdjpy")
    # Refresh module-level aliases that depend on active profile
    import finance_news_tracker.config as config_module

    profile = get_profile("usdjpy")
    config_module.SOURCES = profile.sources
    config_module.FX_KEYWORDS = profile.flat_keywords()


def make_test_settings(
    tmp_path: Path,
    *,
    llm_provider: str = "deepseek",
    profile_id: str = "usdjpy",
) -> Settings:
    data_dir = tmp_path / "data"
    summaries_dir = tmp_path / "summaries"
    log_dir = tmp_path / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    profile = get_profile(profile_id)
    return Settings(
        llm_provider=llm_provider,
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com/v1",
        deepseek_model="deepseek-v4-flash",
        openai_api_key="",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-5.4-mini",
        anthropic_api_key="",
        anthropic_base_url="https://api.anthropic.com/v1",
        anthropic_model="claude-haiku-4-5-20251001",
        data_dir=data_dir,
        summaries_dir=summaries_dir,
        log_dir=log_dir,
        recency_hours=72,
        min_relevance_score=40,
        max_articles_to_score=25,
        request_timeout_seconds=30,
        user_agent="test",
        run_timezone="Asia/Hong_Kong",
        run_weekdays_only=True,
        holiday_guard_enabled=False,
        report_retention_days=90,
        log_level="INFO",
        email_enabled=False,
        smtp_host="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        email_from="",
        email_to=[],
        email_subject_prefix="[Test]",
        email_attach_docx=True,
        tracker_profile_id=profile_id,
        active_profile=profile,
    )
