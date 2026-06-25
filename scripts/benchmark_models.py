"""Development tool: benchmark DeepSeek, OpenAI, and Anthropic on one frozen article set.

中文注解：这不是生产 CLI 命令。用于本地对比不同 provider/model 的评分结果。
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow `python scripts/benchmark_models.py` from repo root without install quirks.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from finance_news_tracker.config import get_settings
from finance_news_tracker.prefilter import rank_for_scoring
from finance_news_tracker.scoring import score_articles_batch
from finance_news_tracker.store import get_store

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_ORDER = ("deepseek", "openai", "anthropic")


@dataclass(frozen=True)
class ModelBenchmarkSummary:
    """Per-provider outcome for a frozen-corpus model benchmark run."""

    provider: str
    model: str
    attempted: int
    scored: int
    skipped: int
    failed: int
    dry_run: bool


def run_model_benchmark(*, dry_run: bool = False) -> list[ModelBenchmarkSummary]:
    """Score the same ranked article set once per provider/model configuration."""
    settings = get_settings()
    store = get_store(settings)
    corpus = store.get_all_articles_for_scoring()
    frozen_items = rank_for_scoring(corpus, settings)
    summaries: list[ModelBenchmarkSummary] = []

    logger.warning(
        "Model benchmark uses one frozen list of %d article(s). With %d providers, "
        "this can plan up to %d scoring call(s).",
        len(frozen_items),
        len(DEFAULT_PROVIDER_ORDER),
        len(frozen_items) * len(DEFAULT_PROVIDER_ORDER),
    )

    for provider_name in DEFAULT_PROVIDER_ORDER:
        llm_config = settings.resolve_llm_config(provider_name)
        already_scored = store.get_scored_article_ids_for(
            llm_config.provider,
            llm_config.model,
        )
        to_score = [
            (article, article_id)
            for article, article_id in frozen_items
            if article_id not in already_scored
        ]
        skipped = len(frozen_items) - len(to_score)

        if dry_run:
            summaries.append(
                ModelBenchmarkSummary(
                    provider=llm_config.provider,
                    model=llm_config.model,
                    attempted=len(to_score),
                    scored=0,
                    skipped=skipped,
                    failed=0,
                    dry_run=True,
                )
            )
            continue

        results = score_articles_batch(
            to_score,
            settings,
            provider=llm_config.provider,
            model=llm_config.model,
        )
        for result in results:
            store.save_score(result)
        summaries.append(
            ModelBenchmarkSummary(
                provider=llm_config.provider,
                model=llm_config.model,
                attempted=len(to_score),
                scored=len(results),
                skipped=skipped,
                failed=len(to_score) - len(results),
                dry_run=False,
            )
        )
    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark LLM providers on one frozen article set (development only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count planned scoring calls without hitting provider APIs",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    summaries = run_model_benchmark(dry_run=args.dry_run)
    for summary in summaries:
        prefix = "Would score" if summary.dry_run else "Scored"
        count = summary.attempted if summary.dry_run else summary.scored
        print(
            f"{summary.provider}/{summary.model}: {prefix} {count} article(s); "
            f"attempted={summary.attempted}, skipped={summary.skipped}, "
            f"failed={summary.failed}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
