from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from finance_news_tracker.config import Settings
from finance_news_tracker.email_delivery import (
    EmailConfigError,
    build_summary_email,
    send_email_with_retry,
    validate_email_settings,
)


def _email_settings(tmp_path: Path) -> Settings:
    return Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        data_dir=tmp_path / "data",
        summaries_dir=tmp_path / "summaries",
        log_dir=tmp_path / "logs",
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
        email_enabled=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@nexaracapital.com",
        smtp_password="secret",
        smtp_use_tls=True,
        smtp_use_ssl=False,
        email_from="sender@nexaracapital.com",
        email_to=["a@example.com", "b@example.com"],
        email_subject_prefix="[TEST]",
        email_attach_docx=True,
    )


def test_validate_email_settings_missing():
    settings = _email_settings(Path("/tmp"))
    settings.smtp_host = ""
    with pytest.raises(EmailConfigError):
        validate_email_settings(settings)


def test_build_summary_email_multi_recipient(tmp_path: Path):
    settings = _email_settings(tmp_path)
    msg = build_summary_email(settings, subject="Test", body_text="Hello")
    assert msg["To"] == "a@example.com, b@example.com"
    assert msg.get_content().strip() == "Hello"


def test_build_summary_email_attaches_docx(tmp_path: Path):
    settings = _email_settings(tmp_path)
    docx = tmp_path / "report.docx"
    docx.write_bytes(b"fake-docx")
    msg = build_summary_email(
        settings,
        subject="Test",
        body_text="Body",
        docx_path=docx,
    )
    assert len(msg.get_payload()) >= 2


@patch("finance_news_tracker.email_delivery._smtp_send")
def test_send_email_with_retry_success(mock_send: MagicMock, tmp_path: Path):
    settings = _email_settings(tmp_path)
    msg = build_summary_email(settings, subject="Test", body_text="Hello")
    send_email_with_retry(msg, settings)
    mock_send.assert_called_once()


@patch("finance_news_tracker.email_delivery.time.sleep")
@patch("finance_news_tracker.email_delivery._smtp_send")
def test_send_email_with_retry_raises_after_failures(
    mock_send: MagicMock,
    mock_sleep: MagicMock,
    tmp_path: Path,
):
    settings = _email_settings(tmp_path)
    mock_send.side_effect = RuntimeError("smtp down")
    msg = build_summary_email(settings, subject="Test", body_text="Hello")
    with pytest.raises(RuntimeError, match="smtp down"):
        send_email_with_retry(msg, settings)
    assert mock_send.call_count == 4
