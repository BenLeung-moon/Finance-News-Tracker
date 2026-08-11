"""Tracker profile abstractions — domain logic lives in profile data, not code branches."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceConfig:
    """Extended news source definition used by collectors and dedupe."""

    id: str
    name: str
    kind: str  # "rss" | "html" | source-specific collector kinds
    url: str
    extra_urls: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["en"])
    link_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    allow_http_statuses: list[int] = field(default_factory=list)
    priority_tier: int = 2
    is_noisy: bool = False
    url_year_templated: bool = False
    allow_pdf: bool = False
    # Prefer RSS `content:encoded` to short feed summaries when available.
    prefer_feed_content: bool = False
    # Optional CSS selectors for card-style HTML list pages (title/date inside <a>).
    # Empty = legacy behaviour: use the whole anchor text + context date parsing.
    # 中文注解：卡片式列表页用选择器精确取标题/日期，未配置时保持原行为。
    title_selector: str = ""
    date_selector: str = ""
    date_formats: list[str] = field(default_factory=list)


@dataclass
class SourceEntityBoostRule:
    """Source-scoped entity match that lightly boosts candidate ranking.

    Used e.g. for Japan Energy Hub EPC names: bonus applies only when
    ``article.source == source_id`` and text matches an alias. Does NOT
    alter LLM ``relevance_score`` or force prefilter pass.
    中文注解：来源限定的实体次级加权，只影响候选排序，不改 LLM 分数。
    """

    source_id: str
    entity_aliases: dict[str, list[str]]
    context_keywords: list[str] = field(default_factory=list)
    entity_bonus: int = 1
    context_bonus: int = 1
    max_bonus: int = 2


@dataclass
class ScoringSchema:
    """Declares LLM scoring output fields for a profile."""

    category_field: str = "category"
    signal_field: str = "signal"
    category_options: list[str] = field(default_factory=list)
    signal_options: list[str] = field(default_factory=list)


@dataclass
class AnalysisSchema:
    """Declares LLM analysis output fields for deeper commercial judgment.

    中文注解：Scoring 轻量筛选；Analysis 产出 Entity / Impact / Suggested Action。
    """

    category_field: str = "category"
    entity_field: str = "entity"
    impact_field: str = "impact"
    suggested_action_field: str = "suggested_action"
    category_options: list[str] = field(default_factory=list)


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
    impact_label: str = "Impact"
    suggested_action_label: str = "Suggested Action"
    entity_label: str = "Entity"
    signal_display: dict[str, str] = field(default_factory=dict)
    default_watchlist: list[str] = field(default_factory=list)
    source_labels: dict[str, str] = field(default_factory=dict)
    fallback_market_read: str = ""


@dataclass
class SummarySection:
    """One renderable block in a Markdown/Word executive memo."""

    id: str
    title: str
    kind: str  # narrative | stories | grouped_stories | watchlist | citations
    max_items: int | None = None
    max_items_docx: int | None = None
    # For grouped_stories: analysis/scoring category ids that belong here
    category_ids: list[str] = field(default_factory=list)
    item_fields: list[str] = field(default_factory=list)
    narrative_field: str | None = None


@dataclass
class SummaryProfile:
    """Pluggable memo style: prompts, sections, LLM output contract, fallbacks."""

    id: str
    system_prompt: str
    sections: list[SummarySection]
    narrative_field: str = "executive_summary"
    narrative_label: str = "Executive Summary"
    fallback_narrative: str = ""
    default_watchlist: list[str] = field(default_factory=list)
    story_fields: list[str] = field(
        default_factory=lambda: ["takeaway", "date", "url", "signal", "relevance"]
    )
    llm_output_fields: dict[str, str] = field(default_factory=dict)
    # Map scoring/analysis category -> section id for grouped layouts
    category_section_map: dict[str, str] = field(default_factory=dict)


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
    # Default collection/summary lookback when RECENCY_HOURS is not explicitly set.
    default_recency_hours: int = 72
    title_fallback_rules: list[TitleFallbackRule] = field(default_factory=list)
    boilerplate_terms: list[str] = field(
        default_factory=lambda: ["breaking", "update", "live", "analysis"]
    )
    # Tier names that receive extra prefilter priority weight
    high_priority_tiers: frozenset[str] = field(default_factory=frozenset)
    # Optional pluggable summary style; None -> BASE_SUMMARY_PROFILE with labels
    summary_profile: SummaryProfile | None = None
    analysis_system_prompt: str = ""
    analysis_schema: AnalysisSchema = field(default_factory=AnalysisSchema)
    # Source-scoped entity ranking boosts (e.g. JEH EPC names); empty for most profiles.
    source_entity_boost_rules: list[SourceEntityBoostRule] = field(default_factory=list)

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

    def resolve_summary_profile(self) -> SummaryProfile:
        """Return the mounted summary profile, defaulting to a labeled base copy.

        中文注解：未显式配置时用 BASE，并把 ReportLabels 中的文案同步进去。
        """
        if self.summary_profile is not None:
            return self.summary_profile

        from finance_news_tracker.profiles.summary_base import build_base_summary_profile

        labels = self.report_labels
        return build_base_summary_profile(
            profile_id=f"{self.id}_summary",
            system_prompt=self.summary_system_prompt,
            narrative_field="market_read",
            narrative_label=labels.market_read_label,
            fallback_narrative=labels.fallback_market_read
            or "Automated LLM synthesis unavailable. See ranked stories below.",
            default_watchlist=list(labels.default_watchlist),
        )
