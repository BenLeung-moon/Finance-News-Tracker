from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Article:
    """Normalized news item from any source."""

    source: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    content_hash: str = ""
    raw_excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.published_at:
            data["published_at"] = self.published_at.isoformat()
        return data


@dataclass
class ScoreResult:
    """DeepSeek relevance scoring output."""

    article_id: int
    relevance_score: int
    fx_channel: str
    likely_usdjpy_direction: str
    confidence: str
    summary: str
    why_it_matters: str
    source_citation: str
    model_raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoredArticle:
    article: Article
    article_id: int
    score: ScoreResult | None = None
    prefilter_hit: bool = False
    keyword_hits: list[str] = field(default_factory=list)
