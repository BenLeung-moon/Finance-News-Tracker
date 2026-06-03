from __future__ import annotations

import argparse
import logging
import sys

from finance_news_tracker.pipeline import run_collect, run_once, run_score, run_summarize


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Local USD/JPY finance news tracker with DeepSeek summaries",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("collect", help="Fetch news from all sources")
    sub.add_parser("score", help="Score unscored articles with DeepSeek")
    sub.add_parser("summarize", help="Generate executive summary markdown")
    sub.add_parser("run-once", help="Collect, score, and summarize in one run")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "collect":
            stats = run_collect()
            print(f"Done. Stats: {stats}")
        elif args.command == "score":
            n = run_score()
            print(f"Scored {n} article(s).")
        elif args.command == "summarize":
            path = run_summarize()
            if path:
                print(f"Summary written to: {path}")
            else:
                print("No summary generated (no scored articles).", file=sys.stderr)
                sys.exit(1)
        elif args.command == "run-once":
            path = run_once()
            if path:
                print(f"Pipeline complete. Summary: {path}")
            else:
                print(
                    "Pipeline finished but no summary was generated. "
                    "Check logs and ensure DEEPSEEK_API_KEY is set.",
                    file=sys.stderr,
                )
                sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
