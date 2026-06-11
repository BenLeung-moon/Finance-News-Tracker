"""Analyze tracker DB for reliability debugging."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _export_side_by_side(conn: sqlite3.Connection, out_path: Path) -> None:
    providers = conn.execute(
        """
        SELECT DISTINCT provider, model
        FROM scores
        ORDER BY provider, model
        """
    ).fetchall()
    rows = conn.execute(
        """
        SELECT a.id, a.title, a.url, s.provider, s.model, s.relevance_score,
               s.likely_usdjpy_direction, s.confidence, s.summary
        FROM articles a
        JOIN scores s ON s.article_id = a.id
        ORDER BY a.id, s.provider, s.model
        """
    ).fetchall()

    by_article: dict[int, dict[str, str | int]] = {}
    for row in rows:
        article_id = int(row["id"])
        record = by_article.setdefault(
            article_id,
            {"article_id": article_id, "title": row["title"], "url": row["url"]},
        )
        label = f"{row['provider']}__{row['model']}"
        record[f"{label}_score"] = row["relevance_score"]
        record[f"{label}_direction"] = row["likely_usdjpy_direction"]
        record[f"{label}_confidence"] = row["confidence"]
        record[f"{label}_summary"] = row["summary"]

    fieldnames = ["article_id", "title", "url"]
    for provider in providers:
        label = f"{provider['provider']}__{provider['model']}"
        fieldnames.extend(
            [
                f"{label}_score",
                f"{label}_direction",
                f"{label}_confidence",
                f"{label}_summary",
            ]
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(by_article.values())
    print(f"\nWrote side-by-side CSV: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze tracker DB scoring results")
    parser.add_argument("--db", type=Path, default=Path("data/tracker.db"))
    parser.add_argument("--csv", type=Path, help="Write side-by-side provider/model CSV")
    args = parser.parse_args()
    db = args.db
    if not db.exists():
        print("No database found. Run collect first.")
        return

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    print("=== Articles by source ===")
    for row in conn.execute(
        "SELECT source, COUNT(*) AS c FROM articles GROUP BY source ORDER BY c DESC"
    ):
        print(f"  {row['source']}: {row['c']}")

    legacy_unscored = conn.execute(
        "SELECT COUNT(*) AS c FROM articles WHERE scored = 0"
    ).fetchone()["c"]
    scored = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()["c"]
    print(f"\nLegacy unscored flag: {legacy_unscored}, Score rows: {scored}")

    print("\n=== Score rows by provider/model ===")
    for row in conn.execute(
        """
        SELECT provider, model, COUNT(*) AS c
        FROM scores
        GROUP BY provider, model
        ORDER BY provider, model
        """
    ):
        print(f"  {row['provider']}/{row['model']}: {row['c']}")

    print("\n=== Scored articles ===")
    rows = conn.execute(
        """
        SELECT a.source, a.title, a.published_at, a.url,
               s.provider, s.model, s.relevance_score, s.likely_usdjpy_direction,
               s.confidence, s.fx_channel, s.summary
        FROM scores s
        JOIN articles a ON a.id = s.article_id
        ORDER BY s.provider, s.model, s.relevance_score DESC
        """
    ).fetchall()

    now = datetime.now(timezone.utc)
    stale = 0
    for r in rows:
        pub = r["published_at"]
        age_days = "unknown"
        if pub:
            try:
                dt = datetime.fromisoformat(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_days = f"{(now - dt).days}d ago"
                if (now - dt).days > 7:
                    stale += 1
            except ValueError:
                pass
        title = (r["title"] or "")[:65]
        print(
            f"{r['provider']}/{r['model']} "
            f"{r['relevance_score']:3d} {r['confidence']:6s} "
            f"{r['likely_usdjpy_direction']:14s} {age_days:10s} {r['source']}"
        )
        print(f"     {title}")

    if rows:
        print("\n=== Score distributions by provider/model ===")
        grouped: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault((row["provider"], row["model"]), []).append(row)
        for (provider, model), group in grouped.items():
            scores = [r["relevance_score"] for r in group]
            conf = Counter(r["confidence"] for r in group)
            dirs = Counter(r["likely_usdjpy_direction"] for r in group)
            print(
                f"{provider}/{model}: range={min(scores)}-{max(scores)}, "
                f"mean={sum(scores)/len(scores):.1f}, confidence={dict(conf)}, "
                f"direction={dict(dirs)}"
            )
        print(f"Articles older than 7 days among scored: {stale}/{len(rows)}")

    no_date = conn.execute(
        "SELECT COUNT(*) AS c FROM articles WHERE published_at IS NULL"
    ).fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
    print(f"\nArticles missing published_at: {no_date}/{total}")

    if args.csv:
        _export_side_by_side(conn, args.csv)


if __name__ == "__main__":
    main()
