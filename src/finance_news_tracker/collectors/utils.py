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


def parse_date_from_text(text: str) -> datetime | None:
    """Parse embedded dates like 'Nov. 7, 2022' from titles or page context."""
    match = TITLE_DATE_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(0).replace(",", ",")
    for fmt in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
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
