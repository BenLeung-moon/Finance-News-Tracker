from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finance_news_tracker.config import get_settings
from finance_news_tracker.email_delivery import send_test_email
from finance_news_tracker.llm import test_provider_llm
from finance_news_tracker.pipeline import (
    run_collect,
    run_once,
    run_score,
    run_summarize,
)
from finance_news_tracker.run_scheduled import (
    run_collect_scheduled_workflow,
    run_scheduled_workflow,
    send_latest_report,
)


def _setup_logging(verbose: bool) -> None:
    settings = get_settings()
    level_name = "DEBUG" if verbose else settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / f"tracker_{datetime.now(ZoneInfo(settings.run_timezone)).strftime('%Y%m%d')}.log"
    handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Multi-profile finance news tracker with LLM summaries",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("collect", help="Fetch news from all sources")
    score_parser = sub.add_parser("score", help="Score articles with an LLM provider")
    score_parser.add_argument("--provider", choices=["deepseek", "openai", "anthropic"])
    score_parser.add_argument("--model", help="Override configured model for provider")
    score_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count planned scoring calls without hitting provider APIs",
    )

    summarize_parser = sub.add_parser(
        "summarize",
        help="Generate executive summary markdown",
    )
    summarize_parser.add_argument(
        "--provider",
        choices=["deepseek", "openai", "anthropic"],
        help="Generate a summary for a specific provider/model",
    )
    summarize_parser.add_argument("--model", help="Override configured model for provider")
    summarize_parser.add_argument(
        "--write-latest-manifest",
        action="store_true",
        help="Write production latest_report.json for this summary",
    )
    run_once_parser = sub.add_parser(
        "run-once",
        help="Collect, score, and summarize in one run",
    )
    run_once_parser.add_argument(
        "--provider",
        choices=["deepseek", "openai", "anthropic"],
        help="Override LLM_PROVIDER for this run",
    )
    run_once_parser.add_argument(
        "--model",
        help="Override configured model for the selected provider",
    )
    sub.add_parser(
        "collect-scheduled",
        help="Production collection only: weekday guard, lock, no LLM, no email",
    )
    test_llm_parser = sub.add_parser(
        "test-llm",
        help="Validate LLM adapter/config wiring, or call the provider if an API key is set",
    )
    test_llm_parser.add_argument("--provider", choices=["deepseek", "openai", "anthropic"])
    test_llm_parser.add_argument("--model", help="Override configured model for provider")
    test_llm_parser.add_argument(
        "--all",
        action="store_true",
        help="Run the connectivity self-test for all providers in fixed order",
    )
    sub.add_parser("test-email", help="Send a test email using SMTP settings")
    sub.add_parser(
        "send-latest-email",
        help="Send the latest manifest-backed report via email",
    )
    sub.add_parser(
        "run-scheduled",
        help="Production workflow: weekday guard, generate, optional email",
    )

    send_parser = sub.choices["send-latest-email"]
    send_parser.add_argument(
        "--path",
        type=Path,
        help="Explicit markdown report path to send (overrides manifest)",
    )
    send_parser.add_argument(
        "--allow-mtime-fallback",
        action="store_true",
        help="If manifest is missing, use newest file by mtime (less safe)",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "collect":
            stats = run_collect()
            print(f"Done. Stats: {stats}")
        elif args.command == "score":
            n = run_score(
                provider=args.provider,
                model=args.model,
                dry_run=args.dry_run,
            )
            verb = "Would score" if args.dry_run else "Scored"
            print(f"{verb} {n} article(s).")
        elif args.command == "summarize":
            report = run_summarize(
                provider=args.provider,
                model=args.model,
                write_latest_manifest=(
                    True if args.write_latest_manifest else None
                ),
            )
            if report:
                print(f"Summary written to: {report.markdown_path}")
            else:
                print("No summary generated (no scored articles).", file=sys.stderr)
                sys.exit(1)
        elif args.command == "run-once":
            report = run_once(provider=args.provider, model=args.model)
            if report:
                print(f"Pipeline complete. Summary: {report.markdown_path}")
            else:
                print(
                    "Pipeline finished but no summary was generated. "
                    "Check logs and ensure the active provider API key is set.",
                    file=sys.stderr,
                )
                sys.exit(1)
        elif args.command == "collect-scheduled":
            stats = run_collect_scheduled_workflow()
            if stats is None:
                print("Scheduled collection skipped (not a valid run day).")
            else:
                print(f"Scheduled collection complete. Stats: {stats}")
        elif args.command == "test-llm":
            settings = get_settings()
            providers = ["deepseek", "openai", "anthropic"] if args.all else [args.provider]
            if providers == [None]:
                providers = [None]
            results = [
                test_provider_llm(
                    settings,
                    provider,
                    model=args.model,
                    timeout_seconds=settings.request_timeout_seconds,
                )
                for provider in providers
            ]
            print(json.dumps(results if args.all else results[0], indent=2))
        elif args.command == "test-email":
            send_test_email(get_settings())
            settings = get_settings()
            print(f"Test email sent to: {', '.join(settings.email_to)}")
        elif args.command == "send-latest-email":
            path = send_latest_report(
                get_settings(),
                markdown_path=args.path,
                allow_mtime_fallback=args.allow_mtime_fallback,
            )
            print(f"Report email sent for: {path}")
        elif args.command == "run-scheduled":
            report = run_scheduled_workflow()
            if report is None:
                print("Scheduled run skipped (not a valid run day).")
            else:
                print(f"Scheduled run complete. Summary: {report.markdown_path}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
