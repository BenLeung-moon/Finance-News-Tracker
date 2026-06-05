import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finance_news_tracker.config import Settings
from finance_news_tracker.manifest import (
    read_latest_report_manifest,
    write_latest_report_manifest,
)


def _settings(tmp_path: Path) -> Settings:
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
    )


def test_write_and_read_latest_report_manifest(tmp_path: Path):
    settings = _settings(tmp_path)
    md = settings.summaries_dir / "usdjpy_summary_20260605_100000.md"
    docx = settings.summaries_dir / "usdjpy_summary_20260605_100000.docx"
    settings.summaries_dir.mkdir(parents=True)
    md.write_text("# test", encoding="utf-8")
    docx.write_bytes(b"docx")

    created = datetime(2026, 6, 5, 10, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))
    write_latest_report_manifest(
        settings,
        run_id="20260605_100000",
        markdown_path=md,
        docx_path=docx,
        created_at=created,
        summary_source_count=3,
    )

    manifest = read_latest_report_manifest(settings)
    assert manifest is not None
    assert manifest.run_id == "20260605_100000"
    assert manifest.markdown_path == str(md)
    assert manifest.docx_path == str(docx)
    assert manifest.summary_source_count == 3

    raw = json.loads(settings.latest_report_manifest_path.read_text(encoding="utf-8"))
    assert raw["timezone"] == "Asia/Hong_Kong"
