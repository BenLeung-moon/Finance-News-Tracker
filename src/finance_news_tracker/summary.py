from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from finance_news_tracker.checker import select_summary_items
from finance_news_tracker.llm_client import chat_completion
from finance_news_tracker.config import Settings
from finance_news_tracker.sources import source_label
from finance_news_tracker.store import Store
from finance_news_tracker.word_export import write_word_summary

logger = logging.getLogger(__name__)
HK_TZ = ZoneInfo("Asia/Hong_Kong")

SUMMARY_SYSTEM_PROMPT = """You are a senior FX strategist writing an executive summary for
USD/JPY traders based on scored financial news (Japan, US policy, and international FX media).

Write in clear English. Be concise and actionable. Do not claim statistical correlation;
frame insights as narrative relevance and market transmission. The per-article relevance
scores are provided to you as context; do not restate or invent numeric scores.

Respond with ONLY valid JSON (no markdown fences):
{
  "market_read": "<one paragraph overall USD/JPY read>",
  "watchlist": ["<upcoming event or risk 1>", "<event 2>", "..."]
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def _format_direction(direction: str) -> str:
    mapping = {
        "usd_jpy_up": "USD/JPY ↑ (yen weaker)",
        "usd_jpy_down": "USD/JPY ↓ (yen stronger)",
        "mixed": "Mixed",
        "unclear": "Unclear",
        "usd_jpy_bullish": "Bullish USD/JPY",
        "usd_jpy_bearish": "Bearish USD/JPY",
    }
    return mapping.get(direction, direction)


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


def _build_summary_prompt(items: list[dict[str, Any]]) -> str:
    lines = []
    for item in items[:12]:
        lines.append(
            f"- [{item['relevance_score']}] {item['title']} "
            f"({source_label(item['source'])})\n"
            f"  URL: {item['url']}\n"
            f"  Channel: {item.get('fx_channel', 'n/a')} | "
            f"Direction: {item.get('likely_usdjpy_direction', 'n/a')} | "
            f"Confidence: {item.get('confidence', 'n/a')}\n"
            f"  Summary: {item.get('summary', '')}\n"
            f"  Why USD/JPY: {item.get('why_it_matters', '')}"
        )
    return "Scored articles for executive summary:\n\n" + "\n\n".join(lines)


def generate_executive_summary_llm(
    items: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, Any]:
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set.")

    payload = {
        "model": settings.deepseek_model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": _build_summary_prompt(items)},
        ],
        "response_format": {"type": "json_object"},
    }
    data = chat_completion(
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        payload=payload,
    )

    content = data["choices"][0]["message"].get("content") or ""
    if not content.strip():
        raise ValueError("DeepSeek returned empty summary content")
    return _extract_json(content)


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
    *,
    citation_items: list[dict[str, Any]] | None = None,
) -> str:
    citations = citation_items if citation_items is not None else items
    watchlist = llm_summary.get("watchlist") or []
    market_read = llm_summary.get("market_read", "")

    lines = [
        "# USD/JPY Executive Summary",
        "",
        f"**Generated:** {_format_generated_time(generated_at)}",
        "**Sources:** BOJ, Nikkei Asia, NHK, Federal Reserve, US Treasury, "
        "FXStreet, Investing.com",
        "",
        "## Market Read",
        "",
        market_read,
        "",
        "## Top Stories",
        "",
    ]

    for i, item in enumerate(items[:7], 1):
        takeaway = item.get("why_it_matters") or item.get("summary", "")
        lines.append(f"### {i}. {item['title']}")
        lines.append(
            f"- **Source:** {source_label(item['source'])} | "
            f"**Direction:** {_format_direction(item['likely_usdjpy_direction'])} | "
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
        lines.append("- Monitor BOJ release calendar and upcoming MPM dates")
        lines.append("- Watch US data (CPI, payrolls) for rate differential moves")

    lines.extend(["", "## Source Citations", ""])
    for item in citations[:15]:
        lines.append(
            f"- [{item['title']}]({item['url']}) — "
            f"{source_label(item['source'])}, {_display_date(item)}"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Generated locally by finance-news-tracker*")
    return "\n".join(lines)


def prepare_summary_items(
    items: list[dict[str, Any]],
    settings: Settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (story_items, citation_items) via checker category quotas and dedupe."""
    return select_summary_items(items, settings)


def write_executive_summary(
    store: Store,
    settings: Settings,
) -> Path | None:
    items = store.get_top_scored(
        settings.min_relevance_score,
        limit=settings.summary_candidate_pool_limit,
        recency_hours=settings.recency_hours,
    )
    if not items:
        items = store.get_recently_scored_all(
            limit=10,
            recency_hours=settings.recency_hours,
        )
    if not items:
        logger.warning("No recent scored articles available for summary.")
        return None

    story_items, citation_items = prepare_summary_items(items, settings)

    now = datetime.now(HK_TZ)
    try:
        llm_summary = generate_executive_summary_llm(story_items, settings)
    except Exception:
        logger.exception("LLM summary failed; using score-only fallback")
        # Top Stories are rendered from `items` regardless, so the fallback only
        # needs the narrative fields.
        llm_summary = {
            "market_read": (
                "Automated LLM synthesis unavailable. See ranked stories below, "
                "scored for USD/JPY relevance per article."
            ),
            "pressure": "unclear",
            "pressure_confidence": "low",
            "watchlist": [
                "BOJ release calendar / next MPM",
                "US CPI and Fed speakers",
                "USD/JPY intervention rhetoric near key levels",
            ],
        }
    body = render_markdown(
        llm_summary,
        story_items,
        now,
        citation_items=citation_items,
    )

    settings.summaries_dir.mkdir(parents=True, exist_ok=True)
    stem = f"usdjpy_summary_{now.strftime('%Y%m%d_%H%M%S')}"
    path = settings.summaries_dir / f"{stem}.md"
    path.write_text(body, encoding="utf-8")

    try:
        docx_path = write_word_summary(
            llm_summary,
            story_items,
            now,
            settings.summaries_dir / f"{stem}.docx",
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
    )
    logger.info("Wrote executive summary to %s", path)
    return path
