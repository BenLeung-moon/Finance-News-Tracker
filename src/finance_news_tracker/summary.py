from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from finance_news_tracker.analysis import (
    analyze_items_batch,
    merge_analysis_into_items,
)
from finance_news_tracker.config import Settings
from finance_news_tracker.dedupe import (
    dedupe_scored_items,
    diversify_scored_items,
)
from finance_news_tracker.llm import LlmConfig, complete_json
from finance_news_tracker.manifest import GeneratedReport, write_latest_report_manifest
from finance_news_tracker.profiles.base import SummaryProfile, SummarySection
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
            f"  Entity: {item.get('entity', 'n/a')}\n"
            f"  Summary: {item.get('summary', '')}\n"
            f"  {labels.why_it_matters_label}: {item.get('why_it_matters', '')}\n"
            f"  {labels.impact_label}: {item.get('impact', '')}\n"
            f"  {labels.suggested_action_label}: {item.get('suggested_action', '')}"
        )
    return "Scored articles for executive summary:\n\n" + "\n\n".join(lines)


def generate_executive_summary_llm(
    items: list[dict[str, Any]],
    settings: Settings,
    *,
    llm_config: LlmConfig | None = None,
) -> dict[str, Any]:
    config = llm_config or settings.resolve_analysis_llm_config()
    summary_profile = settings.active_profile.resolve_summary_profile()
    parsed, _content = complete_json(
        config,
        system_prompt=summary_profile.system_prompt,
        user_prompt=_build_summary_prompt(items, settings),
        temperature=0.3,
        max_tokens=1200,
        timeout_seconds=120.0,
    )
    return parsed


def _items_for_section(
    section: SummarySection,
    items: list[dict[str, Any]],
    summary_profile: SummaryProfile,
) -> list[dict[str, Any]]:
    if section.kind == "stories":
        limit = section.max_items or 7
        return items[:limit]
    if section.kind == "grouped_stories":
        wanted = set(section.category_ids)
        if summary_profile.category_section_map:
            # Also accept categories that map to this section id
            for cat, section_id in summary_profile.category_section_map.items():
                if section_id == section.id:
                    wanted.add(cat)
        matched = [
            item
            for item in items
            if str(item.get("analysis_category") or item.get("category") or "")
            in wanted
        ]
        limit = section.max_items or 5
        return matched[:limit]
    if section.kind == "citations":
        limit = section.max_items or 10
        return items[:limit]
    return []


def _story_takeaway(item: dict[str, Any]) -> str:
    return (
        item.get("impact")
        or item.get("why_it_matters")
        or item.get("summary")
        or ""
    )


def _render_story_block(
    item: dict[str, Any],
    index: int,
    settings: Settings,
    fields: list[str],
) -> list[str]:
    profile = settings.active_profile
    labels = profile.report_labels
    lines = [f"### {index}. {item['title']}"]
    meta_parts: list[str] = [
        f"**Source:** {profile.source_label(item['source'])}"
    ]
    if "signal" in fields:
        signal = profile.format_signal(str(item.get("signal", "")))
        meta_parts.append(f"**{labels.signal_label}:** {signal}")
    if "relevance" in fields:
        meta_parts.append(
            f"**Relevance:** {_relevance_label(item.get('relevance_score'))}"
        )
    if "entity" in fields and item.get("entity"):
        meta_parts.append(f"**{labels.entity_label}:** {item['entity']}")
    lines.append("- " + " | ".join(meta_parts))

    if "takeaway" in fields:
        takeaway = _story_takeaway(item)
        if takeaway:
            lines.append(f"- {takeaway}")
    if "impact" in fields and item.get("impact"):
        lines.append(f"- **{labels.impact_label}:** {item['impact']}")
    if "suggested_action" in fields and item.get("suggested_action"):
        lines.append(
            f"- **{labels.suggested_action_label}:** {item['suggested_action']}"
        )
    if "date" in fields or "url" in fields:
        date_part = _display_date(item) if "date" in fields else ""
        if "url" in fields:
            link = f"[Read more]({item['url']})"
            if date_part:
                lines.append(f"- **Date:** {date_part} | {link}")
            else:
                lines.append(f"- {link}")
        elif date_part:
            lines.append(f"- **Date:** {date_part}")
    lines.append("")
    return lines


def render_markdown(
    llm_summary: dict[str, Any],
    items: list[dict[str, Any]],
    generated_at: datetime,
    settings: Settings,
    *,
    scoring_provider: str,
    scoring_model: str,
    analysis_provider: str,
    analysis_model: str,
    citation_items: list[dict[str, Any]] | None = None,
) -> str:
    """Render memo from the active SummaryProfile sections (no profile-id branches)."""
    profile = settings.active_profile
    labels = profile.report_labels
    summary_profile = profile.resolve_summary_profile()
    citations = citation_items if citation_items is not None else items

    lines = [
        f"# {labels.report_title}",
        "",
        f"**Generated:** {_format_generated_time(generated_at)}",
        f"**Scoring LLM:** {scoring_provider} / {scoring_model}",
        f"**Analysis LLM:** {analysis_provider} / {analysis_model}",
        f"**Profile:** {profile.id}",
        f"**Summary style:** {summary_profile.id}",
        f"**Sources:** {labels.sources_line}",
        "",
    ]

    for section in summary_profile.sections:
        if section.kind == "narrative":
            field_name = section.narrative_field or summary_profile.narrative_field
            narrative = llm_summary.get(field_name) or llm_summary.get("market_read") or ""
            if not narrative:
                narrative = (
                    summary_profile.fallback_narrative
                    or labels.fallback_market_read
                )
            lines.extend([f"## {section.title}", "", str(narrative), ""])
            continue

        if section.kind in {"stories", "grouped_stories"}:
            section_items = _items_for_section(section, items, summary_profile)
            lines.extend([f"## {section.title}", ""])
            if not section_items:
                lines.extend(["_No items in this section._", ""])
                continue
            fields = section.item_fields or summary_profile.story_fields
            for i, item in enumerate(section_items, 1):
                lines.extend(_render_story_block(item, i, settings, fields))
            continue

        if section.kind == "watchlist":
            watchlist = llm_summary.get("watchlist") or []
            if not watchlist:
                watchlist = (
                    summary_profile.default_watchlist or labels.default_watchlist
                )
            lines.extend([f"## {section.title}", ""])
            for w in watchlist:
                lines.append(f"- {w}")
            lines.append("")
            continue

        if section.kind == "citations":
            limit = section.max_items or 10
            citation_source = citations if citation_items is not None else items
            # Prefer broader citation list when provided
            citation_pool = citations if section.id == "citations" else citation_source
            lines.extend([f"## {section.title}", ""])
            for item in citation_pool[:limit]:
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


def _ensure_analyses(
    store: Store,
    story_items: list[dict[str, Any]],
    settings: Settings,
    *,
    scoring_provider: str,
    scoring_model: str,
    analysis_config: LlmConfig,
) -> list[dict[str, Any]]:
    """Load cached analyses or run Analysis role; upsert Tracker rows."""
    profile = settings.active_profile
    article_ids = [int(item["id"]) for item in story_items]
    existing = store.get_analyses_for_articles(
        article_ids,
        profile_id=profile.id,
        scoring_provider=scoring_provider,
        scoring_model=scoring_model,
        analysis_provider=analysis_config.provider,
        analysis_model=analysis_config.model,
    )
    missing = [item for item in story_items if int(item["id"]) not in existing]
    new_results = []
    if missing:
        new_results = analyze_items_batch(
            missing,
            settings,
            scoring_provider=scoring_provider,
            scoring_model=scoring_model,
            analysis_provider=analysis_config.provider,
            analysis_model=analysis_config.model,
        )
        for result in new_results:
            store.save_analysis(result)

    all_analyses = list(existing.values()) + new_results
    by_id = {a.article_id: a for a in all_analyses}
    for item in story_items:
        analysis = by_id.get(int(item["id"]))
        if analysis:
            store.upsert_tracker_item_from_analysis(article=item, analysis=analysis)
    return merge_analysis_into_items(story_items, all_analyses)


def write_executive_summary(
    store: Store,
    settings: Settings,
    *,
    provider: str | None = None,
    model: str | None = None,
    scoring_provider: str | None = None,
    scoring_model: str | None = None,
    analysis_provider: str | None = None,
    analysis_model: str | None = None,
    write_latest_manifest: bool = True,
) -> GeneratedReport | None:
    """Generate Analysis-enriched memo using scoring + analysis model roles.

    Backward compatible: ``provider``/``model`` alone still work and apply to
    both roles when role-specific args are omitted.
    """
    profile = settings.active_profile
    labels = profile.report_labels
    summary_profile = profile.resolve_summary_profile()

    # Legacy single-role args fill both sides when role-specific ones are absent.
    score_provider_arg = scoring_provider if scoring_provider is not None else provider
    score_model_arg = scoring_model if scoring_model is not None else model
    analysis_provider_arg = (
        analysis_provider if analysis_provider is not None else provider
    )
    analysis_model_arg = analysis_model if analysis_model is not None else model

    scoring_config = settings.resolve_scoring_llm_config(
        score_provider_arg, score_model_arg
    )
    analysis_config = settings.resolve_analysis_llm_config(
        analysis_provider_arg, analysis_model_arg
    )

    source_ids = set(profile.source_by_id())
    items = store.get_top_scored(
        settings.min_relevance_score,
        limit=15,
        recency_hours=settings.recency_hours,
        provider=scoring_config.provider,
        model=scoring_config.model,
        source_ids=source_ids,
    )
    if not items:
        items = store.get_recently_scored_all(
            limit=10,
            recency_hours=settings.recency_hours,
            provider=scoring_config.provider,
            model=scoring_config.model,
            source_ids=source_ids,
        )
    if not items:
        logger.warning("No recent scored articles available for summary.")
        return None

    story_items, citation_items = prepare_summary_items(items, settings)
    story_items = _ensure_analyses(
        store,
        story_items,
        settings,
        scoring_provider=scoring_config.provider,
        scoring_model=scoring_config.model,
        analysis_config=analysis_config,
    )
    # Keep citations aligned with analysis enrichment where possible
    citation_items = merge_analysis_into_items(
        citation_items,
        list(
            store.get_analyses_for_articles(
                [int(i["id"]) for i in citation_items],
                profile_id=profile.id,
                scoring_provider=scoring_config.provider,
                scoring_model=scoring_config.model,
                analysis_provider=analysis_config.provider,
                analysis_model=analysis_config.model,
            ).values()
        ),
    )

    now = datetime.now(HK_TZ)
    narrative_field = summary_profile.narrative_field
    try:
        llm_summary = generate_executive_summary_llm(
            story_items,
            settings,
            llm_config=analysis_config,
        )
    except Exception:
        logger.exception("LLM summary failed; using score-only fallback")
        llm_summary = {
            narrative_field: (
                summary_profile.fallback_narrative or labels.fallback_market_read
            ),
            "market_read": (
                summary_profile.fallback_narrative or labels.fallback_market_read
            ),
            "watchlist": list(
                summary_profile.default_watchlist or labels.default_watchlist
            ),
        }

    body = render_markdown(
        llm_summary,
        story_items,
        now,
        settings,
        scoring_provider=scoring_config.provider,
        scoring_model=scoring_config.model,
        analysis_provider=analysis_config.provider,
        analysis_model=analysis_config.model,
        citation_items=citation_items,
    )

    settings.summaries_dir.mkdir(parents=True, exist_ok=True)
    run_id = now.strftime("%Y%m%d_%H%M%S")
    score_suffix = (
        f"{_safe_filename_part(scoring_config.provider)}_"
        f"{_safe_filename_part(scoring_config.model)}"
    )
    analysis_suffix = (
        f"{_safe_filename_part(analysis_config.provider)}_"
        f"{_safe_filename_part(analysis_config.model)}"
    )
    if score_suffix == analysis_suffix:
        stem = f"{labels.filename_prefix}_{run_id}_{analysis_suffix}"
    else:
        stem = (
            f"{labels.filename_prefix}_{run_id}_"
            f"score-{score_suffix}_analysis-{analysis_suffix}"
        )
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
            scoring_provider=scoring_config.provider,
            scoring_model=scoring_config.model,
            analysis_provider=analysis_config.provider,
            analysis_model=analysis_config.model,
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
        provider=analysis_config.provider,
        model=analysis_config.model,
        scoring_provider=scoring_config.provider,
        scoring_model=scoring_config.model,
        analysis_provider=analysis_config.provider,
        analysis_model=analysis_config.model,
    )
    if write_latest_manifest:
        write_latest_report_manifest(
            settings,
            run_id=run_id,
            markdown_path=path,
            docx_path=docx_path,
            created_at=now,
            summary_source_count=len(story_items),
            provider=analysis_config.provider,
            model=analysis_config.model,
            scoring_provider=scoring_config.provider,
            scoring_model=scoring_config.model,
            analysis_provider=analysis_config.provider,
            analysis_model=analysis_config.model,
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
        provider=analysis_config.provider,
        model=analysis_config.model,
        scoring_provider=scoring_config.provider,
        scoring_model=scoring_config.model,
        analysis_provider=analysis_config.provider,
        analysis_model=analysis_config.model,
    )
