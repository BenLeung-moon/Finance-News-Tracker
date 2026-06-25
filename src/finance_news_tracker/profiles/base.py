"""Tracker profile abstractions — domain logic lives in profile data, not code branches."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceConfig:
    """Extended news source definition used by collectors and dedupe."""

    id: str
    name: str
    kind: str  # "rss" | "html"
    url: str
    extra_urls: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["en"])
    link_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    priority_tier: int = 2
    is_noisy: bool = False
    url_year_templated: bool = False


@dataclass
class ScoringSchema:
    """Declares LLM scoring output fields for a profile."""

    category_field: str = "category"
    signal_field: str = "signal"
    category_options: list[str] = field(default_factory=list)
    signal_options: list[str] = field(default_factory=list)


@dataclass
class TitleFallbackRule:
    """Pass an article when title matches even without keyword hits."""

    source_prefix: str
    pattern: str
    tag: str


@dataclass
class ReportLabels:
    """Human-readable report strings and source display names."""

    report_title: str
    filename_prefix: str
    sources_line: str
    market_read_label: str = "Market Read"
    why_it_matters_label: str = "Why it matters"
    category_label: str = "Category"
    signal_label: str = "Signal"
    signal_display: dict[str, str] = field(default_factory=dict)
    default_watchlist: list[str] = field(default_factory=list)
    source_labels: dict[str, str] = field(default_factory=dict)
    fallback_market_read: str = ""


@dataclass
class TrackerProfile:
    """Complete configuration for one tracking theme."""

    id: str
    name: str
    keyword_tiers: dict[str, list[str]]
    sources: list[SourceConfig]
    scoring_system_prompt: str
    scoring_schema: ScoringSchema
    summary_system_prompt: str
    noisy_source_ids: frozenset[str]
    report_labels: ReportLabels
    title_fallback_rules: list[TitleFallbackRule] = field(default_factory=list)
    boilerplate_terms: list[str] = field(
        default_factory=lambda: ["breaking", "update", "live", "analysis"]
    )
    # Tier names that receive extra prefilter priority weight
    high_priority_tiers: frozenset[str] = field(default_factory=frozenset)

    def source_by_id(self) -> dict[str, SourceConfig]:
        return {s.id: s for s in self.sources}

    def flat_keywords(self) -> list[str]:
        """Deduplicated union of all keyword tiers (order preserved)."""
        seen: set[str] = set()
        out: list[str] = []
        for words in self.keyword_tiers.values():
            for w in words:
                key = w.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(w)
        return out

    def source_label(self, source_id: str) -> str:
        return self.report_labels.source_labels.get(source_id, source_id)

    def format_signal(self, value: str) -> str:
        return self.report_labels.signal_display.get(value, value)
