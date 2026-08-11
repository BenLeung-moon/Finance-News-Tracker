from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from finance_news_tracker.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class GeneratedReport:
    """Artifacts produced by a single successful summary generation."""

    run_id: str
    markdown_path: Path
    docx_path: Path | None
    created_at: datetime
    story_count: int
    article_count: int
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    scoring_provider: str = ""
    scoring_model: str = ""
    analysis_provider: str = ""
    analysis_model: str = ""


@dataclass
class ReportManifest:
    """Pointer to the latest successfully generated report.

    Written by run-once after generation; read by send-latest-email so delivery
    does not guess from file mtimes and accidentally send a stale report.
    """

    run_id: str
    markdown_path: str
    docx_path: str | None
    created_at: str
    timezone: str
    summary_source_count: int
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    scoring_provider: str = ""
    scoring_model: str = ""
    analysis_provider: str = ""
    analysis_model: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReportManifest:
        provider = str(data.get("provider", "deepseek"))
        model = str(data.get("model", "deepseek-chat"))
        return cls(
            run_id=str(data["run_id"]),
            markdown_path=str(data["markdown_path"]),
            docx_path=data.get("docx_path"),
            created_at=str(data["created_at"]),
            timezone=str(data.get("timezone", "Asia/Hong_Kong")),
            summary_source_count=int(data.get("summary_source_count", 0)),
            provider=provider,
            model=model,
            scoring_provider=str(data.get("scoring_provider") or provider),
            scoring_model=str(data.get("scoring_model") or model),
            analysis_provider=str(data.get("analysis_provider") or provider),
            analysis_model=str(data.get("analysis_model") or model),
        )


def write_latest_report_manifest(
    settings: Settings,
    *,
    run_id: str,
    markdown_path: Path,
    docx_path: Path | None,
    created_at: datetime,
    summary_source_count: int,
    provider: str = "deepseek",
    model: str = "deepseek-chat",
    scoring_provider: str = "",
    scoring_model: str = "",
    analysis_provider: str = "",
    analysis_model: str = "",
) -> Path:
    """Record the exact artifacts from the current generation run."""
    manifest = ReportManifest(
        run_id=run_id,
        markdown_path=str(markdown_path),
        docx_path=str(docx_path) if docx_path and docx_path.exists() else None,
        created_at=created_at.isoformat(),
        timezone=settings.run_timezone,
        summary_source_count=summary_source_count,
        provider=provider,
        model=model,
        scoring_provider=scoring_provider or provider,
        scoring_model=scoring_model or model,
        analysis_provider=analysis_provider or provider,
        analysis_model=analysis_model or model,
    )
    path = settings.latest_report_manifest_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Wrote latest report manifest to %s", path)
    return path


def read_latest_report_manifest(settings: Settings) -> ReportManifest | None:
    path = settings.latest_report_manifest_path
    if not path.exists():
        logger.warning("No latest report manifest at %s", path)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ReportManifest.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        logger.exception("Failed to parse report manifest at %s", path)
        return None


def find_latest_markdown_by_mtime(summaries_dir: Path) -> Path | None:
    """Fallback only: sort by mtime when manifest is missing (e.g. manual resend)."""
    candidates = sorted(
        summaries_dir.glob("usdjpy_summary_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None
