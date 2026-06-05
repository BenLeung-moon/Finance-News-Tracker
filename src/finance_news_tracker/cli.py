from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finance_news_tracker.config import get_settings
from finance_news_tracker.email_delivery import send_test_email
from finance_news_tracker.pipeline import run_collect, run_once, run_score, run_summarize
from finance_news_tracker.run_scheduled import run_scheduled_workflow, send_latest_report


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
        description="USD/JPY finance news tracker with DeepSeek summaries",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("collect", help="Fetch news from all sources")
    sub.add_parser("score", help="Score unscored articles with DeepSeek")
    sub.add_parser("summarize", help="Generate executive summary markdown")
    sub.add_parser("run-once", help="Collect, score, and summarize in one run")
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
            n = run_score()
            print(f"Scored {n} article(s).")
        elif args.command == "summarize":
            report = run_summarize()
            if report:
                print(f"Summary written to: {report.markdown_path}")
            else:
                print("No summary generated (no scored articles).", file=sys.stderr)
                sys.exit(1)
        elif args.command == "run-once":
            report = run_once()
            if report:
                print(f"Pipeline complete. Summary: {report.markdown_path}")
            else:
                print(
                    "Pipeline finished but no summary was generated. "
                    "Check logs and ensure DEEPSEEK_API_KEY is set.",
                    file=sys.stderr,
                )
                sys.exit(1)
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
