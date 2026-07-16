"""Shared base summary profile — reusable Executive Memo template.

中文注解：业务 profile 可完整替换，也可基于本模板只覆盖 prompt / 栏目 / 标签。
"""

from __future__ import annotations

from copy import deepcopy

from finance_news_tracker.profiles.base import (
    SummaryProfile,
    SummarySection,
)


BASE_SUMMARY_SYSTEM_PROMPT = """You are writing a concise executive intelligence memo
from scored news items.

Write in clear English. Be actionable. Do not invent facts beyond the provided items.
Do not restate numeric relevance scores.

Respond with ONLY valid JSON (no markdown fences):
{
  "executive_summary": "<one paragraph overall read>",
  "watchlist": ["<upcoming event or risk 1>", "<event 2>", "..."]
}
"""


def build_base_summary_profile(
    *,
    profile_id: str = "base",
    system_prompt: str | None = None,
    narrative_field: str = "executive_summary",
    narrative_label: str = "Executive Summary",
    fallback_narrative: str = (
        "Automated LLM synthesis unavailable. See ranked stories below."
    ),
    default_watchlist: list[str] | None = None,
    top_stories_max: int = 7,
    citations_max_md: int = 10,
    citations_max_docx: int = 15,
    story_fields: list[str] | None = None,
    extra_sections: list[SummarySection] | None = None,
    replace_sections: list[SummarySection] | None = None,
) -> SummaryProfile:
    """Build a summary profile, optionally overriding sections or labels.

    中文注解：`replace_sections` 完全替换默认栏目；`extra_sections` 插在 Top Stories 之后。
    """
    fields = story_fields or ["takeaway", "date", "url", "signal", "relevance"]
    if replace_sections is not None:
        sections = list(replace_sections)
    else:
        sections = [
            SummarySection(
                id="executive_summary",
                title=narrative_label,
                kind="narrative",
                narrative_field=narrative_field,
            ),
            SummarySection(
                id="top_stories",
                title="Top Stories",
                kind="stories",
                max_items=top_stories_max,
                item_fields=list(fields),
            ),
        ]
        if extra_sections:
            sections.extend(extra_sections)
        sections.extend(
            [
                SummarySection(
                    id="watchlist",
                    title="Watchlist",
                    kind="watchlist",
                ),
                SummarySection(
                    id="citations",
                    title="Source Citations",
                    kind="citations",
                    max_items=citations_max_md,
                    max_items_docx=citations_max_docx,
                ),
            ]
        )

    return SummaryProfile(
        id=profile_id,
        system_prompt=system_prompt or BASE_SUMMARY_SYSTEM_PROMPT,
        narrative_field=narrative_field,
        narrative_label=narrative_label,
        fallback_narrative=fallback_narrative,
        default_watchlist=list(default_watchlist or []),
        sections=sections,
        story_fields=list(fields),
        llm_output_fields={
            narrative_field: "string",
            "watchlist": "string[]",
        },
    )


BASE_SUMMARY_PROFILE = build_base_summary_profile()


def derive_summary_profile(
    base: SummaryProfile | None = None,
    **overrides: object,
) -> SummaryProfile:
    """Shallow-copy a summary profile and apply field overrides.

    中文注解：用于业务 profile 在 base 上做局部定制，避免整份模板复制粘贴。
    """
    source = deepcopy(base or BASE_SUMMARY_PROFILE)
    for key, value in overrides.items():
        if not hasattr(source, key):
            raise AttributeError(f"SummaryProfile has no field '{key}'")
        setattr(source, key, value)
    return source
