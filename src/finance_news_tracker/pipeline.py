from __future__ import annotations

import logging

from finance_news_tracker.collectors import collect_all
from finance_news_tracker.config import get_settings
from finance_news_tracker.manifest import GeneratedReport
from finance_news_tracker.prefilter import rank_for_scoring
from finance_news_tracker.scoring import score_articles_batch
from finance_news_tracker.store import get_store
from finance_news_tracker.summary import write_executive_summary

logger = logging.getLogger(__name__)


def run_collect() -> dict[str, int]:
    settings = get_settings()
    store = get_store(settings)
    articles = collect_all(settings, skip_hashes=store.get_existing_hashes())

    new_count = 0
    for article in articles:
        _, is_new = store.upsert_article(article)
        if is_new:
            new_count += 1

    stats = store.stats()
    stats["new_this_run"] = new_count
    return stats


def run_score(
    provider: str | None = None,
    model: str | None = None,
    *,
    dry_run: bool = False,
    frozen_items: list[tuple] | None = None,
) -> int:
    settings = get_settings()
    store = get_store(settings)
    llm_config = settings.resolve_scoring_llm_config(provider, model)
    unscored = (
        frozen_items
        if frozen_items is not None
        else store.get_unscored_for(
            llm_config.provider,
            llm_config.model,
            source_ids=set(settings.active_profile.source_by_id()),
        )
    )
    if not unscored:
        logger.info(
            "No unscored articles for scoring %s/%s.",
            llm_config.provider,
            llm_config.model,
        )
        return 0

    to_score = list(unscored) if frozen_items is not None else rank_for_scoring(unscored, settings)
    if not to_score:
        logger.info("No articles passed ranking for scoring.")
        return 0

    already_scored = store.get_scored_article_ids_for(llm_config.provider, llm_config.model)
    to_score = [(article, article_id) for article, article_id in to_score if article_id not in already_scored]
    if dry_run:
        logger.info(
            "Dry run: would score %d article(s) for %s/%s.",
            len(to_score),
            llm_config.provider,
            llm_config.model,
        )
        return len(to_score)

    results = score_articles_batch(
        to_score,
        settings,
        provider=llm_config.provider,
        model=llm_config.model,
    )
    for result in results:
        store.save_score(result)
    return len(results)


def run_summarize(
    provider: str | None = None,
    model: str | None = None,
    *,
    scoring_provider: str | None = None,
    scoring_model: str | None = None,
    analysis_provider: str | None = None,
    analysis_model: str | None = None,
    write_latest_manifest: bool | None = None,
) -> GeneratedReport | None:
    settings = get_settings()
    store = get_store(settings)
    explicit_provider = any(
        value is not None
        for value in (
            provider,
            model,
            scoring_provider,
            scoring_model,
            analysis_provider,
            analysis_model,
        )
    )
    should_write_manifest = (
        not explicit_provider if write_latest_manifest is None else write_latest_manifest
    )
    return write_executive_summary(
        store,
        settings,
        provider=provider,
        model=model,
        scoring_provider=scoring_provider,
        scoring_model=scoring_model,
        analysis_provider=analysis_provider,
        analysis_model=analysis_model,
        write_latest_manifest=should_write_manifest,
    )


def run_once(
    provider: str | None = None,
    model: str | None = None,
    *,
    scoring_provider: str | None = None,
    scoring_model: str | None = None,
    analysis_provider: str | None = None,
    analysis_model: str | None = None,
) -> GeneratedReport | None:
    """Full production pipeline: collect → score → analyze/summarize.

    Role-specific provider/model can differ. Legacy ``provider``/``model`` still
    apply to both roles when role args are omitted.
    """
    stats = run_collect()
    logger.info("Collect stats: %s", stats)

    score_provider = scoring_provider if scoring_provider is not None else provider
    score_model = scoring_model if scoring_model is not None else model
    scored = run_score(provider=score_provider, model=score_model)
    logger.info("Scored %d articles", scored)

    return run_summarize(
        provider=provider,
        model=model,
        scoring_provider=scoring_provider if scoring_provider is not None else provider,
        scoring_model=scoring_model if scoring_model is not None else model,
        analysis_provider=analysis_provider if analysis_provider is not None else provider,
        analysis_model=analysis_model if analysis_model is not None else model,
        write_latest_manifest=True,
    )
