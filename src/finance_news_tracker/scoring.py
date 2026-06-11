from __future__ import annotations

import logging
import time

from finance_news_tracker.config import Settings
from finance_news_tracker.llm import LlmConfig, complete_json
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
    *,
    llm_config: LlmConfig | None = None,
) -> ScoreResult:
    config = llm_config or settings.resolve_llm_config()
    parsed, content = complete_json(
        config,
        system_prompt=SCORING_SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(article),
        temperature=0.2,
        max_tokens=1000,
        timeout_seconds=120.0,
    )

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
        provider=config.provider,
        model=config.model,
        model_raw=content,
    )


def score_articles_batch(
    items: list[tuple[Article, int]],
    settings: Settings,
    delay_seconds: float = 0.5,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> list[ScoreResult]:
    config = settings.resolve_llm_config(provider, model)
    results: list[ScoreResult] = []
    for i, (article, article_id) in enumerate(items):
        try:
            result = score_article(article, article_id, settings, llm_config=config)
            results.append(result)
            logger.info(
                "Scored [%d/%d] %s/%s %s -> %d",
                i + 1,
                len(items),
                config.provider,
                config.model,
                article.title[:60],
                result.relevance_score,
            )
        except Exception:
            logger.exception("Failed to score article id=%d", article_id)
        if i < len(items) - 1:
            time.sleep(delay_seconds)
    return results
