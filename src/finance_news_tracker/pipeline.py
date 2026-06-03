from __future__ import annotations

import logging
from pathlib import Path

from finance_news_tracker.collectors import collect_all
from finance_news_tracker.config import get_settings
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


def run_score() -> int:
    settings = get_settings()
    store = get_store(settings)
    unscored = store.get_unscored_articles()
    if not unscored:
        logger.info("No unscored articles.")
        return 0

    to_score = rank_for_scoring(unscored, settings)
    if not to_score:
        logger.info("No articles passed ranking for scoring.")
        return 0

    results = score_articles_batch(to_score, settings)
    for result in results:
        store.save_score(result)
    return len(results)


def run_summarize() -> Path | None:
    settings = get_settings()
    store = get_store(settings)
    return write_executive_summary(store, settings)


def run_once() -> Path | None:
    stats = run_collect()
    logger.info("Collect stats: %s", stats)
    scored = run_score()
    logger.info("Scored %d articles", scored)
    return run_summarize()
