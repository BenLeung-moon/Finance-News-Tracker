from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article, ScoreResult

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """You are a senior FX strategist analyzing financial news
(Japan, US policy, international FX) for relevance to USD/JPY (US dollar vs Japanese yen).

Score each article for how likely it is to move or inform USD/JPY trading in the near term.
This is explanatory relevance, not statistical correlation.

Respond with ONLY valid JSON (no markdown fences) matching this schema:
{
  "relevance_score": <integer 0-100>,
  "fx_channel": "<one of: monetary_policy, rates_differential, inflation, intervention, risk_sentiment, trade_commodities, growth_data, fiscal_policy, other>",
  "likely_usdjpy_direction": "<one of: usd_jpy_up, usd_jpy_down, mixed, unclear>",
  "confidence": "<one of: low, medium, high>",
  "summary": "<2-3 sentence summary>",
  "why_it_matters": "<1-2 sentences on USD/JPY transmission mechanism>",
  "source_citation": "<title and source in one line>"
}

Scoring guide:
- 80-100: Direct BOJ/Fed policy, intervention, major CPI/rates surprise
- 60-79: Strong macro with clear yen channel (wages, JGB, oil shock to Japan)
- 40-59: Indirect but meaningful (trade, risk-off, fiscal)
- 20-39: Weak or tangential
- 0-19: Not relevant to USD/JPY
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty model response")
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


def _build_user_prompt(article: Article) -> str:
    published = (
        article.published_at.isoformat() if article.published_at else "unknown"
    )
    return f"""Analyze this news item for USD/JPY relevance:

Source: {article.source}
Title: {article.title}
URL: {article.url}
Published: {published}
Summary/Excerpt: {article.summary or article.raw_excerpt or "(none)"}
"""


def score_article(
    article: Article,
    article_id: int,
    settings: Settings,
) -> ScoreResult:
    if not settings.deepseek_api_key:
        raise ValueError(
            "DEEPSEEK_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(article)},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    parsed = _extract_json(content)

    return ScoreResult(
        article_id=article_id,
        relevance_score=int(parsed.get("relevance_score", 0)),
        fx_channel=str(parsed.get("fx_channel", "other")),
        likely_usdjpy_direction=str(
            parsed.get("likely_usdjpy_direction", "unclear")
        ),
        confidence=str(parsed.get("confidence", "low")),
        summary=str(parsed.get("summary", "")),
        why_it_matters=str(parsed.get("why_it_matters", "")),
        source_citation=str(
            parsed.get("source_citation", f"{article.title} ({article.source})")
        ),
        model_raw=content,
    )


def score_articles_batch(
    items: list[tuple[Article, int]],
    settings: Settings,
    delay_seconds: float = 0.5,
) -> list[ScoreResult]:
    results: list[ScoreResult] = []
    for i, (article, article_id) in enumerate(items):
        try:
            result = score_article(article, article_id, settings)
            results.append(result)
            logger.info(
                "Scored [%d/%d] %s -> %d",
                i + 1,
                len(items),
                article.title[:60],
                result.relevance_score,
            )
        except Exception:
            logger.exception("Failed to score article id=%d", article_id)
        if i < len(items) - 1:
            time.sleep(delay_seconds)
    return results
