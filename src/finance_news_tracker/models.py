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
    """Provider/model-specific relevance scoring output."""

    article_id: int
    relevance_score: int
    category: str
    signal: str
    confidence: str
    summary: str
    why_it_matters: str
    source_citation: str
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    model_raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    """Deeper commercial judgment produced by the Analysis model role.

    中文注解：绑定 scoring provider/model，保证分析可复现且不会混读评分。
    """

    article_id: int
    profile_id: str
    scoring_provider: str
    scoring_model: str
    analysis_provider: str
    analysis_model: str
    category: str
    entity: str
    impact: str
    suggested_action: str
    model_raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrackerItem:
    """Persistent Policy & Competitor Tracker row with human action fields."""

    article_id: int
    profile_id: str
    scoring_provider: str
    scoring_model: str
    analysis_provider: str
    analysis_model: str
    title: str
    source: str
    original_link: str
    category: str
    summary: str
    relevance_score: int
    entity: str
    impact: str
    suggested_action: str
    item_date: str | None = None
    owner: str | None = None
    status: str = "pending"
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoredArticle:
    article: Article
    article_id: int
    score: ScoreResult | None = None
    prefilter_hit: bool = False
    keyword_hits: list[str] = field(default_factory=list)
