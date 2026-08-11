from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

TITLE_DATE_PATTERN = re.compile(
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{1,2},?\s+\d{4}",
    re.IGNORECASE,
)

# Japanese date: 2026年3月25日
JA_DATE_PATTERN = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

# Numeric dates: 2026/3/25, 2026.03.25, 2026-03-25
NUMERIC_DATE_PATTERN = re.compile(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})")

# Compact Japanese corporate release dates in URLs: 260709j0101.pdf -> 2026-07-09
YYMMDD_DATE_PATTERN = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")


def parse_date_from_text(text: str) -> datetime | None:
    """Parse embedded dates from titles or page context (EN + JA + numeric)."""
    match = TITLE_DATE_PATTERN.search(text)
    if match:
        raw = match.group(0).replace(",", ",")
        for fmt in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    match = JA_DATE_PATTERN.search(text)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(y, m, d, tzinfo=timezone.utc)
        except ValueError:
            pass

    match = NUMERIC_DATE_PATTERN.search(text)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(y, m, d, tzinfo=timezone.utc)
        except ValueError:
            pass

    match = YYMMDD_DATE_PATTERN.search(text)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(2000 + y, m, d, tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def parse_datetime_attr(value: str) -> datetime | None:
    """Parse ISO-like datetime from HTML <time datetime=\"...\"> attributes."""
    if not value:
        return None
    cleaned = value.strip()
    # Date-only values
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        try:
            return datetime.strptime(cleaned, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None


def enrich_published_at(article) -> None:
    """Fill missing published_at from title/summary when possible."""
    if article.published_at is not None:
        return
    for blob in (article.title, article.summary, article.raw_excerpt):
        if not blob:
            continue
        parsed = parse_date_from_text(blob)
        if parsed:
            article.published_at = parsed
            return


def content_hash(source: str, title: str, url: str) -> str:
    raw = f"{source}|{title}|{url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def within_recency(published_at: datetime | None, recency_hours: int) -> bool:
    # 无发布日期的条目不视为“最新”，避免旧文被当成新闻
    if published_at is None:
        return False
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_hours = (now - published_at).total_seconds() / 3600
    return age_hours <= recency_hours

