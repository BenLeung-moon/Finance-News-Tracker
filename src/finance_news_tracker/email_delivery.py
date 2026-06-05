from __future__ import annotations

import logging
import mimetypes
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from finance_news_tracker.config import Settings

logger = logging.getLogger(__name__)

# Bounded retry: transient SMTP failures should not fail silently, but we also
# avoid infinite loops that would block cron indefinitely.
SMTP_RETRY_DELAYS_SECONDS = (10, 30, 60)


class EmailConfigError(ValueError):
    """Raised when required SMTP settings are missing for an email command."""


def validate_email_settings(settings: Settings) -> None:
    """Validate SMTP config when an email command is invoked."""
    missing: list[str] = []
    if not settings.smtp_host:
        missing.append("SMTP_HOST")
    if not settings.smtp_username:
        missing.append("SMTP_USERNAME")
    if not settings.smtp_password:
        missing.append("SMTP_PASSWORD")
    if not settings.email_from:
        missing.append("EMAIL_FROM")
    if not settings.email_to:
        missing.append("EMAIL_TO")
    if missing:
        raise EmailConfigError(
            "Missing required email settings: " + ", ".join(missing)
        )


def build_summary_email(
    settings: Settings,
    *,
    subject: str,
    body_text: str,
    markdown_path: Path | None = None,
    docx_path: Path | None = None,
) -> EmailMessage:
    """Build a multipart email with plain-text body and optional .docx attachment."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = ", ".join(settings.email_to)
    msg.set_content(body_text)

    attach_docx = settings.email_attach_docx and docx_path and docx_path.exists()
    if attach_docx:
        mime_type, _ = mimetypes.guess_type(str(docx_path))
        maintype, subtype = (
            mime_type.split("/", 1)
            if mime_type and "/" in mime_type
            else (
                "application",
                "vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        )
        msg.add_attachment(
            docx_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=docx_path.name,
        )
    elif markdown_path and markdown_path.exists():
        logger.debug(
            "No docx attachment for %s; email body contains markdown text only.",
            markdown_path,
        )
    return msg


def _smtp_send(msg: EmailMessage, settings: Settings) -> None:
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def send_email_with_retry(msg: EmailMessage, settings: Settings) -> None:
    """Send via SMTP with bounded retries; raises on final failure."""
    validate_email_settings(settings)
    last_error: Exception | None = None
    attempts = len(SMTP_RETRY_DELAYS_SECONDS) + 1
    for attempt in range(1, attempts + 1):
        try:
            _smtp_send(msg, settings)
            logger.info(
                "Email sent to %s (attempt %d/%d)",
                ", ".join(settings.email_to),
                attempt,
                attempts,
            )
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "SMTP send failed (attempt %d/%d): %s",
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                delay = SMTP_RETRY_DELAYS_SECONDS[attempt - 1]
                time.sleep(delay)
    assert last_error is not None
    raise last_error


def send_test_email(settings: Settings) -> None:
    """Send a minimal test message to all configured recipients."""
    subject = f"{settings.email_subject_prefix} SMTP test"
    body = (
        "This is a test email from finance-news-tracker.\n\n"
        "If you received this message, SMTP settings are working.\n"
    )
    msg = build_summary_email(settings, subject=subject, body_text=body)
    send_email_with_retry(msg, settings)


def send_report_email(
    settings: Settings,
    *,
    markdown_path: Path,
    docx_path: Path | None = None,
    subject_override: str | None = None,
) -> None:
    """Send an existing report by path (used by send-latest-email / run-scheduled)."""
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown report not found: {markdown_path}")

    body_text = markdown_path.read_text(encoding="utf-8")
    subject = subject_override or (
        f"{settings.email_subject_prefix} USD/JPY Executive Summary "
        f"({markdown_path.stem})"
    )
    msg = build_summary_email(
        settings,
        subject=subject,
        body_text=body_text,
        markdown_path=markdown_path,
        docx_path=docx_path,
    )
    send_email_with_retry(msg, settings)
