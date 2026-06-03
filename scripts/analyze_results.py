"""Analyze tracker DB for reliability debugging."""
from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    db = Path("data/tracker.db")
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

    unscored = conn.execute(
        "SELECT COUNT(*) AS c FROM articles WHERE scored = 0"
    ).fetchone()["c"]
    scored = conn.execute("SELECT COUNT(*) AS c FROM scores").fetchone()["c"]
    print(f"\nUnscored: {unscored}, Scored: {scored}")

    print("\n=== Scored articles ===")
    rows = conn.execute(
        """
        SELECT a.source, a.title, a.published_at, a.url,
               s.relevance_score, s.likely_usdjpy_direction,
               s.confidence, s.fx_channel, s.summary
        FROM scores s
        JOIN articles a ON a.id = s.article_id
        ORDER BY s.relevance_score DESC
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
            f"{r['relevance_score']:3d} {r['confidence']:6s} "
            f"{r['likely_usdjpy_direction']:14s} {age_days:10s} {r['source']}"
        )
        print(f"     {title}")

    if rows:
        scores = [r["relevance_score"] for r in rows]
        conf = Counter(r["confidence"] for r in rows)
        dirs = Counter(r["likely_usdjpy_direction"] for r in rows)
        print(f"\nScore range: {min(scores)}-{max(scores)}, mean={sum(scores)/len(scores):.1f}")
        print(f"Confidence: {dict(conf)}")
        print(f"Direction: {dict(dirs)}")
        print(f"Articles older than 7 days among scored: {stale}/{len(rows)}")

    no_date = conn.execute(
        "SELECT COUNT(*) AS c FROM articles WHERE published_at IS NULL"
    ).fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
    print(f"\nArticles missing published_at: {no_date}/{total}")


if __name__ == "__main__":
    main()
