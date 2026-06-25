from __future__ import annotations

import logging
import time

from finance_news_tracker.config import Settings
from finance_news_tracker.llm import LlmConfig, complete_json
from finance_news_tracker.models import Article, ScoreResult

logger = logging.getLogger(__name__)


def _build_user_prompt(article: Article, settings: Settings) -> str:
    profile = settings.active_profile
    published = (
        article.published_at.isoformat() if article.published_at else "unknown"
    )
    return f"""Analyze this news item for {profile.name} relevance:

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
    profile = settings.active_profile
    schema = profile.scoring_schema
    parsed, content = complete_json(
        config,
        system_prompt=profile.scoring_system_prompt,
        user_prompt=_build_user_prompt(article, settings),
        temperature=0.2,
        max_tokens=1000,
        timeout_seconds=120.0,
    )

    return ScoreResult(
        article_id=article_id,
        relevance_score=int(parsed.get("relevance_score", 0)),
        category=str(parsed.get(schema.category_field, "other")),
        signal=str(parsed.get(schema.signal_field, "unclear")),
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
