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


from tests.conftest import make_test_settings


def _email_settings(tmp_path: Path) -> Settings:
    settings = make_test_settings(tmp_path)
    settings.email_enabled = True
    settings.smtp_host = "smtp.example.com"
    settings.smtp_port = 587
    settings.smtp_username = "sender@nexaracapital.com"
    settings.smtp_password = "secret"
    settings.email_from = "sender@nexaracapital.com"
    settings.email_to = ["a@example.com", "b@example.com"]
    settings.email_subject_prefix = "[TEST]"
    return settings


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
