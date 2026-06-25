from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from finance_news_tracker.config import Settings
from finance_news_tracker.dedupe import (
    dedupe_scored_items,
    diversify_scored_items,
)
from finance_news_tracker.llm import LlmConfig, complete_json
from finance_news_tracker.manifest import GeneratedReport, write_latest_report_manifest
from finance_news_tracker.store import Store
from finance_news_tracker.word_export import write_word_summary

logger = logging.getLogger(__name__)
HK_TZ = ZoneInfo("Asia/Hong_Kong")


def _to_hk(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(HK_TZ)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_generated_time(generated_at: datetime) -> str:
    return f"{_to_hk(generated_at).strftime('%Y-%m-%d %H:%M')} HK time"


def _relevance_label(score: Any) -> str:
    try:
        value = int(score)
    except (TypeError, ValueError):
        value = 0
    if value >= 80:
        return "High"
    if value >= 60:
        return "Medium"
    return "Low"


def _build_summary_prompt(items: list[dict[str, Any]], settings: Settings) -> str:
    profile = settings.active_profile
    labels = profile.report_labels
    lines = []
    for item in items[:12]:
        lines.append(
            f"- [{item['relevance_score']}] {item['title']} "
            f"({profile.source_label(item['source'])})\n"
            f"  URL: {item['url']}\n"
            f"  {labels.category_label}: {item.get('category', 'n/a')} | "
            f"{labels.signal_label}: {item.get('signal', 'n/a')} | "
            f"Confidence: {item.get('confidence', 'n/a')}\n"
            f"  Summary: {item.get('summary', '')}\n"
            f"  {labels.why_it_matters_label}: {item.get('why_it_matters', '')}"
        )
    return "Scored articles for executive summary:\n\n" + "\n\n".join(lines)


def generate_executive_summary_llm(
    items: list[dict[str, Any]],
    settings: Settings,
    *,
    llm_config: LlmConfig | None = None,
) -> dict[str, Any]:
    config = llm_config or settings.resolve_llm_config()
    parsed, _content = complete_json(
        config,
        system_prompt=settings.active_profile.summary_system_prompt,
        user_prompt=_build_summary_prompt(items, settings),
        temperature=0.3,
        max_tokens=1200,
        timeout_seconds=120.0,
    )
    return parsed


def _display_date(item: dict[str, Any]) -> str:
    """Prefer the real publication date; fall back to the first-seen date for
    undated items (e.g. Nikkei RSS), labelled so it is not mistaken for exact."""
    pub = item.get("published_at")
    if pub:
        parsed = _parse_datetime(pub)
        if parsed:
            return _to_hk(parsed).strftime("%Y-%m-%d")
        return str(pub)[:10]
    collected = item.get("collected_at")
    if collected:
        parsed = _parse_datetime(collected)
        if parsed:
            return f"~{_to_hk(parsed).strftime('%Y-%m-%d')} (first seen)"
        return f"~{str(collected)[:10]} (first seen)"
    return "date unknown"


def render_markdown(
    llm_summary: dict[str, Any],
    items: list[dict[str, Any]],
    generated_at: datetime,
    settings: Settings,
    *,
    provider: str,
    model: str,
    citation_items: list[dict[str, Any]] | None = None,
) -> str:
    profile = settings.active_profile
    labels = profile.report_labels
    citations = citation_items if citation_items is not None else items
    watchlist = llm_summary.get("watchlist") or []
    market_read = llm_summary.get("market_read", "")

    lines = [
        f"# {labels.report_title}",
        "",
        f"**Generated:** {_format_generated_time(generated_at)}",
        f"**LLM:** {provider} / {model}",
        f"**Profile:** {profile.id}",
        f"**Sources:** {labels.sources_line}",
        "",
        f"## {labels.market_read_label}",
        "",
        market_read,
        "",
        "## Top Stories",
        "",
    ]

    for i, item in enumerate(items[:7], 1):
        takeaway = item.get("why_it_matters") or item.get("summary", "")
        signal = profile.format_signal(str(item.get("signal", "")))
        lines.append(f"### {i}. {item['title']}")
        lines.append(
            f"- **Source:** {profile.source_label(item['source'])} | "
            f"**{labels.signal_label}:** {signal} | "
            f"**Relevance:** {_relevance_label(item.get('relevance_score'))}"
        )
        lines.append(f"- {takeaway}")
        lines.append(f"- **Date:** {_display_date(item)} | [Read more]({item['url']})")
        lines.append("")

    lines.extend(["## Watchlist", ""])
    if watchlist:
        for w in watchlist:
            lines.append(f"- {w}")
    else:
        for w in labels.default_watchlist:
            lines.append(f"- {w}")

    lines.extend(["", "## Source Citations", ""])
    for item in citations[:10]:
        lines.append(
            f"- [{item['title']}]({item['url']}) — "
            f"{profile.source_label(item['source'])}, {_display_date(item)}"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Generated locally by finance-news-tracker*")
    return "\n".join(lines)


def prepare_summary_items(
    items: list[dict[str, Any]],
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (story_items, citation_items): diverse top stories, broader deduped citations."""
    threshold = settings.dedupe_similarity_threshold
    story_items = diversify_scored_items(
        items,
        max_items=12,
        max_per_source=settings.summary_max_per_source,
        threshold=threshold,
        settings=settings,
    )
    if not story_items:
        story_items = dedupe_scored_items(items, threshold, settings, max_items=12)
    citation_items = dedupe_scored_items(items, threshold, settings, max_items=15)
    return story_items, citation_items


def _safe_filename_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return safe.strip("-") or "unknown"


def write_executive_summary(
    store: Store,
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    write_latest_manifest: bool = True,
) -> GeneratedReport | None:
    profile = settings.active_profile
    labels = profile.report_labels
    llm_config = settings.resolve_llm_config(provider, model)
    items = store.get_top_scored(
        settings.min_relevance_score,
        limit=15,
        recency_hours=settings.recency_hours,
        provider=llm_config.provider,
        model=llm_config.model,
    )
    if not items:
        items = store.get_recently_scored_all(
            limit=10,
            recency_hours=settings.recency_hours,
            provider=llm_config.provider,
            model=llm_config.model,
        )
    if not items:
        logger.warning("No recent scored articles available for summary.")
        return None

    story_items, citation_items = prepare_summary_items(items, settings)

    now = datetime.now(HK_TZ)
    try:
        llm_summary = generate_executive_summary_llm(
            story_items,
            settings,
            llm_config=llm_config,
        )
    except Exception:
        logger.exception("LLM summary failed; using score-only fallback")
        llm_summary = {
            "market_read": labels.fallback_market_read,
            "watchlist": list(labels.default_watchlist),
        }
    body = render_markdown(
        llm_summary,
        story_items,
        now,
        settings,
        provider=llm_config.provider,
        model=llm_config.model,
        citation_items=citation_items,
    )

    settings.summaries_dir.mkdir(parents=True, exist_ok=True)
    run_id = now.strftime("%Y%m%d_%H%M%S")
    provider_suffix = _safe_filename_part(llm_config.provider)
    model_suffix = _safe_filename_part(llm_config.model)
    stem = f"{labels.filename_prefix}_{run_id}_{provider_suffix}_{model_suffix}"
    path = settings.summaries_dir / f"{stem}.md"
    path.write_text(body, encoding="utf-8")

    docx_path: Path | None = None
    try:
        docx_path = write_word_summary(
            llm_summary,
            story_items,
            now,
            settings.summaries_dir / f"{stem}.docx",
            settings=settings,
            citation_items=citation_items,
        )
        logger.info("Wrote Word summary to %s", docx_path)
    except Exception:
        logger.exception("Word export failed; Markdown summary still written")

    top_score = max((i["relevance_score"] for i in items), default=0)
    store.save_summary_run(
        file_path=str(path),
        body=body,
        article_count=len(items),
        top_score=top_score,
        provider=llm_config.provider,
        model=llm_config.model,
    )
    if write_latest_manifest:
        write_latest_report_manifest(
            settings,
            run_id=run_id,
            markdown_path=path,
            docx_path=docx_path,
            created_at=now,
            summary_source_count=len(story_items),
            provider=llm_config.provider,
            model=llm_config.model,
        )
    else:
        logger.info("Skipped latest_report.json for benchmark summary %s", path)
    logger.info("Wrote executive summary to %s", path)
    return GeneratedReport(
        run_id=run_id,
        markdown_path=path,
        docx_path=docx_path,
        created_at=now,
        story_count=len(story_items),
        article_count=len(items),
        provider=llm_config.provider,
        model=llm_config.model,
    )
