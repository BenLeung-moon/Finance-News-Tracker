import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finance_news_tracker.config import Settings
from finance_news_tracker.manifest import (
    read_latest_report_manifest,
    write_latest_report_manifest,
)


from tests.conftest import make_test_settings


def _settings(tmp_path: Path) -> Settings:
    return make_test_settings(tmp_path)


def test_write_and_read_latest_report_manifest(tmp_path: Path):
    settings = _settings(tmp_path)
    md = settings.summaries_dir / "usdjpy_summary_20260605_100000.md"
    docx = settings.summaries_dir / "usdjpy_summary_20260605_100000.docx"
    settings.summaries_dir.mkdir(parents=True, exist_ok=True)
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
        provider="deepseek",
        model="deepseek-v4-flash",
    )

    manifest = read_latest_report_manifest(settings)
    assert manifest is not None
    assert manifest.run_id == "20260605_100000"
    assert manifest.markdown_path == str(md)
    assert manifest.docx_path == str(docx)
    assert manifest.summary_source_count == 3
    assert manifest.provider == "deepseek"
    assert manifest.model == "deepseek-v4-flash"

    raw = json.loads(settings.latest_report_manifest_path.read_text(encoding="utf-8"))
    assert raw["timezone"] == "Asia/Hong_Kong"
