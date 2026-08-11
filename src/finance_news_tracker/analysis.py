"""Analysis role: commercial impact judgment + memo synthesis inputs.

中文注解：本轮使用单次结构化 LLM 调用；AnalysisContextProvider 预留只读上下文扩展，
不开放模型自主 tool calling。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from finance_news_tracker.config import Settings
from finance_news_tracker.llm import LlmConfig, complete_json
from finance_news_tracker.models import AnalysisResult
from finance_news_tracker.profiles.base import AnalysisSchema

logger = logging.getLogger(__name__)


class AnalysisContextProvider(Protocol):
    """Read-only context builder for Analysis calls (extensible later)."""

    def build_item_context(
        self,
        item: dict[str, Any],
        *,
        related_items: list[dict[str, Any]],
        settings: Settings,
    ) -> dict[str, Any]:
        ...


class DefaultAnalysisContextProvider:
    """Default context: current article, score fields, and related batch titles."""

    def build_item_context(
        self,
        item: dict[str, Any],
        *,
        related_items: list[dict[str, Any]],
        settings: Settings,
    ) -> dict[str, Any]:
        related = [
            {
                "title": r.get("title"),
                "source": r.get("source"),
                "category": r.get("category"),
                "relevance_score": r.get("relevance_score"),
            }
            for r in related_items
            if r.get("id") != item.get("id")
        ][:8]
        return {
            "article": {
                "id": item.get("id"),
                "source": item.get("source"),
                "title": item.get("title"),
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "summary": item.get("summary") or "",
                "why_it_matters": item.get("why_it_matters") or "",
                "category": item.get("category"),
                "signal": item.get("signal"),
                "relevance_score": item.get("relevance_score"),
                "confidence": item.get("confidence"),
            },
            "related_scored_items": related,
            "profile_id": settings.active_profile.id,
        }


def _default_analysis_prompt(profile_name: str, schema: AnalysisSchema) -> str:
    categories = ", ".join(schema.category_options) or "other"
    return f"""You are a senior analyst writing commercial impact judgments for {profile_name}.

For each news item, explain the entity involved, business impact, and whether internal
follow-up is warranted. Be concise and actionable. Do not invent facts.

Respond with ONLY valid JSON (no markdown fences):
{{
  "{schema.category_field}": "<one of: {categories}>",
  "{schema.entity_field}": "<company, agency, project, or 'n/a'>",
  "{schema.impact_field}": "<1-2 sentences on commercial / strategic impact>",
  "{schema.suggested_action_field}": "<concrete follow-up, or 'Monitor only'>"
}}
"""


def _build_user_prompt(context: dict[str, Any]) -> str:
    article = context.get("article") or {}
    related = context.get("related_scored_items") or []
    related_lines = [
        f"- [{r.get('relevance_score')}] {r.get('title')} ({r.get('source')})"
        for r in related
    ]
    related_block = "\n".join(related_lines) if related_lines else "(none)"
    return f"""Analyze this scored news item:

Title: {article.get('title')}
Source: {article.get('source')}
URL: {article.get('url')}
Published: {article.get('published_at') or 'unknown'}
Scoring category: {article.get('category')}
Signal: {article.get('signal')}
Relevance: {article.get('relevance_score')}
Confidence: {article.get('confidence')}
Score summary: {article.get('summary')}
Why it matters (scoring): {article.get('why_it_matters')}

Related scored items in this batch:
{related_block}
"""


def analyze_item(
    item: dict[str, Any],
    settings: Settings,
    *,
    scoring_provider: str,
    scoring_model: str,
    llm_config: LlmConfig,
    related_items: list[dict[str, Any]] | None = None,
    context_provider: AnalysisContextProvider | None = None,
) -> AnalysisResult:
    profile = settings.active_profile
    schema = profile.analysis_schema
    provider = context_provider or DefaultAnalysisContextProvider()
    context = provider.build_item_context(
        item,
        related_items=related_items or [],
        settings=settings,
    )
    system_prompt = profile.analysis_system_prompt or _default_analysis_prompt(
        profile.name, schema
    )
    parsed, content = complete_json(
        llm_config,
        system_prompt=system_prompt,
        user_prompt=_build_user_prompt(context),
        temperature=0.2,
        max_tokens=800,
        timeout_seconds=120.0,
    )
    category = str(
        parsed.get(schema.category_field)
        or item.get("category")
        or "other"
    )
    return AnalysisResult(
        article_id=int(item["id"]),
        profile_id=profile.id,
        scoring_provider=scoring_provider,
        scoring_model=scoring_model,
        analysis_provider=llm_config.provider,
        analysis_model=llm_config.model,
        category=category,
        entity=str(parsed.get(schema.entity_field, "n/a") or "n/a"),
        impact=str(
            parsed.get(schema.impact_field)
            or item.get("why_it_matters")
            or item.get("summary")
            or ""
        ),
        suggested_action=str(
            parsed.get(schema.suggested_action_field) or "Monitor only"
        ),
        model_raw=content,
    )


def analyze_items_batch(
    items: list[dict[str, Any]],
    settings: Settings,
    *,
    scoring_provider: str,
    scoring_model: str,
    analysis_provider: str | None = None,
    analysis_model: str | None = None,
    delay_seconds: float = 0.5,
    context_provider: AnalysisContextProvider | None = None,
) -> list[AnalysisResult]:
    """Run Analysis on scored items; skips items that already have analysis later in store."""
    config = settings.resolve_analysis_llm_config(analysis_provider, analysis_model)
    results: list[AnalysisResult] = []
    for i, item in enumerate(items):
        try:
            result = analyze_item(
                item,
                settings,
                scoring_provider=scoring_provider,
                scoring_model=scoring_model,
                llm_config=config,
                related_items=items,
                context_provider=context_provider,
            )
            results.append(result)
            logger.info(
                "Analyzed [%d/%d] %s/%s id=%s -> %s",
                i + 1,
                len(items),
                config.provider,
                config.model,
                item.get("id"),
                result.category,
            )
        except Exception:
            logger.exception("Failed to analyze article id=%s", item.get("id"))
            # Fallback analysis from scoring fields so Tracker/Memo still work
            results.append(
                AnalysisResult(
                    article_id=int(item["id"]),
                    profile_id=settings.active_profile.id,
                    scoring_provider=scoring_provider,
                    scoring_model=scoring_model,
                    analysis_provider=config.provider,
                    analysis_model=config.model,
                    category=str(item.get("category") or "other"),
                    entity="n/a",
                    impact=str(item.get("why_it_matters") or item.get("summary") or ""),
                    suggested_action="Monitor only",
                    model_raw="",
                )
            )
        if i < len(items) - 1:
            time.sleep(delay_seconds)
    return results


def merge_analysis_into_items(
    items: list[dict[str, Any]],
    analyses: list[AnalysisResult],
) -> list[dict[str, Any]]:
    """Attach analysis fields onto scored item dicts for summary rendering."""
    by_id = {a.article_id: a for a in analyses}
    merged: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        analysis = by_id.get(int(item["id"]))
        if analysis:
            row["analysis_category"] = analysis.category
            row["entity"] = analysis.entity
            row["impact"] = analysis.impact
            row["suggested_action"] = analysis.suggested_action
            # Prefer analysis category for section grouping when present
            row["category"] = analysis.category or row.get("category")
        merged.append(row)
    return merged
