from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from finance_news_tracker.config import Settings, get_settings
from finance_news_tracker.email_delivery import send_report_email
from finance_news_tracker.manifest import (
    GeneratedReport,
    read_latest_report_manifest,
)
from finance_news_tracker.pipeline import run_once
from finance_news_tracker.scheduling import acquire_run_lock, should_run_scheduled
from finance_news_tracker.store import get_store

logger = logging.getLogger(__name__)


def cleanup_old_reports(settings: Settings) -> int:
    """Remove report files older than REPORT_RETENTION_DAYS."""
    if settings.report_retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.report_retention_days
    )
    removed = 0
    for pattern in ("usdjpy_summary_*.md", "usdjpy_summary_*.docx"):
        for path in settings.summaries_dir.glob(pattern):
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
    if removed:
        logger.info("Removed %d old report file(s)", removed)
    return removed


def send_latest_report(
    settings: Settings,
    *,
    markdown_path: Path | None = None,
    allow_mtime_fallback: bool = False,
) -> Path:
    """Send the manifest-backed latest report, or an explicit path if given."""
    from finance_news_tracker.manifest import find_latest_markdown_by_mtime

    docx_path: Path | None = None
    if markdown_path is None:
        manifest = read_latest_report_manifest(settings)
        if manifest:
            markdown_path = Path(manifest.markdown_path)
            docx_path = Path(manifest.docx_path) if manifest.docx_path else None
        elif allow_mtime_fallback:
            markdown_path = find_latest_markdown_by_mtime(settings.summaries_dir)
            if markdown_path:
                candidate = markdown_path.with_suffix(".docx")
                docx_path = candidate if candidate.exists() else None
        else:
            raise FileNotFoundError(
                "No latest_report.json manifest found. Run run-once first, or pass "
                "--path explicitly. Mtime fallback is disabled by default to avoid "
                "sending a stale report after a failed generation."
            )
    else:
        candidate = markdown_path.with_suffix(".docx")
        docx_path = candidate if candidate.exists() else None

    if markdown_path is None or not markdown_path.exists():
        raise FileNotFoundError("No markdown report available to send.")

    send_report_email(
        settings,
        markdown_path=markdown_path,
        docx_path=docx_path,
    )
    return markdown_path


def run_scheduled_workflow(settings: Settings | None = None) -> GeneratedReport | None:
    """Deployment orchestration: weekday guard, lock, generate, optional email.

    Keeps generation (run_once) and delivery (send_report_email) decoupled so
    core pipeline changes on other branches do not entangle with SMTP/Docker.
    """
    settings = settings or get_settings()
    store = get_store(settings)
    run_id = datetime.now(ZoneInfo(settings.run_timezone)).strftime("%Y%m%d_%H%M%S")

    if not should_run_scheduled(settings):
        logger.info(
            "Skipping scheduled run: not a valid run day in %s",
            settings.run_timezone,
        )
        return None

    history_id = store.create_run_history(
        run_id=run_id,
        trigger_type="scheduled",
        llm_model=settings.deepseek_model,
    )

    try:
        with acquire_run_lock(settings.run_lock_path):
            report = run_once()
            if report is None:
                raise RuntimeError(
                    "Pipeline finished but no summary was generated."
                )

            email_sent = False
            recipients: str | None = None
            if settings.email_enabled:
                send_report_email(
                    settings,
                    markdown_path=report.markdown_path,
                    docx_path=report.docx_path,
                )
                email_sent = True
                recipients = ", ".join(settings.email_to)

            cleanup_old_reports(settings)
            store.finish_run_history(
                history_id,
                status="success",
                markdown_path=str(report.markdown_path),
                docx_path=str(report.docx_path) if report.docx_path else None,
                email_sent=email_sent,
                email_recipients=recipients,
                source_count=report.article_count,
                story_count=report.story_count,
            )
            return report
    except Exception as exc:
        logger.exception("Scheduled run failed")
        store.finish_run_history(
            history_id,
            status="failed",
            error_message=str(exc),
        )
        raise
