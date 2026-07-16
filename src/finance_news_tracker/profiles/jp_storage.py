"""Japan energy storage ecosystem profile — sources from Websites to Track.docx."""

from __future__ import annotations

from finance_news_tracker.profiles.base import (
    AnalysisSchema,
    ReportLabels,
    ScoringSchema,
    SourceConfig,
    SummarySection,
    TrackerProfile,
)
from finance_news_tracker.profiles.summary_base import build_base_summary_profile

# Common HTML exclude patterns for Japanese corporate/government news pages
_COMMON_EXCLUDES = [
    "#",
    "javascript:",
    ".pdf",
    ".zip",
    "/tag/",
    "/tags/",
    "/category/",
    "/search",
    "/login",
    "/contact",
    "facebook.com",
    "twitter.com",
    "linkedin.com",
    "youtube.com",
]

_POLICY_KEYWORDS = [
    "capacity market",
    "long-term decarbonized power source auction",
    "long term decarbonized power source auction",
    "demand response",
    "demand adjustment market",
    "bess",
    "battery storage",
    "battery energy storage",
    "grid-scale storage",
    "energy storage",
    "storage roadmap",
    "vpp",
    "virtual power plant",
    "容量市場",
    "長期脱炭電源オークション",
    "需給調整市場",
    "系統用蓄電池",
    "蓄電池",
    "電力貯蔵",
    "蓄電池・電源産業戦略",
    "蓄電池・電源産業",
    "エネルギー貯蔵",
    "定置型蓄電池",
    "蓄電所",
]

_PROJECT_KEYWORDS = [
    "new battery storage",
    "battery storage project",
    "storage plant",
    "commercial operation",
    "commence operation",
    "grid connection",
    "project finance",
    "financing",
    "construction",
    "新設",
    "商業運転",
    "運転開始",
    "稼働開始",
    "プロジェクトファイナンス",
    "融資",
    "着工",
    "竣工",
    "系統連系",
]

_COMPANY_KEYWORDS = [
    "investment",
    "joint venture",
    "partnership",
    "collaboration",
    "alliance",
    "order",
    "contract",
    "acquisition",
    "出資",
    "提携",
    "合弁",
    "受注",
    "協業",
    "共同開発",
    "買収",
    "出資比率",
]

SCORING_SYSTEM_PROMPT = """You are a senior Japan power-market analyst scoring news for relevance
to the Japan energy storage ecosystem (policy, market mechanisms, project deployment,
financing, and corporate activity).

Score each article for how likely it is to inform tracking of Japan's battery storage /
grid-scale storage market in the near term. This is narrative relevance, not statistical correlation.

Respond with ONLY valid JSON (no markdown fences) matching this schema:
{
  "relevance_score": <integer 0-100>,
  "category": "<one of: policy_market, project_deployment, corporate_activity, technology_supply_chain, financing, other>",
  "signal": "<one of: positive, negative, neutral, n/a>",
  "confidence": "<one of: low, medium, high>",
  "summary": "<2-3 sentence summary in clear English>",
  "why_it_matters": "<1-2 sentences on why this matters for Japan storage ecosystem tracking>",
  "source_citation": "<title and source in one line>"
}

Scoring guide:
- 80-100: Major policy/market rule change, large storage project FID/COD, major corporate deal
- 60-79: Meaningful project or partnership news with clear storage angle
- 40-59: Indirect but relevant (grid, renewables, power market adjacent)
- 20-39: Weak or tangential
- 0-19: Not relevant to Japan storage tracking
"""

SUMMARY_SYSTEM_PROMPT = """You are a senior Japan power-market analyst writing a Weekly
Intelligence Memo for a Japan BESS platform team.

Write in clear English. Be concise and actionable. Cover policy, OCCTO/grid, market rules,
competitors, and financing/M&A. Explain business implications without inventing facts.

Respond with ONLY valid JSON (no markdown fences):
{
  "executive_summary": "<one paragraph overall Japan BESS platform read>",
  "watchlist": ["<upcoming event or risk 1>", "<event 2>", "..."]
}
"""

ANALYSIS_SYSTEM_PROMPT = """You are a senior Japan BESS commercial analyst.

For each scored item, classify it into the memo taxonomy, name the entity involved,
explain Impact on BESS platform strategy, and suggest an internal follow-up action.

Respond with ONLY valid JSON (no markdown fences):
{
  "category": "<one of: policy, occto_grid, market_rules, competitors, financing_ma, other>",
  "entity": "<company, agency, project, or n/a>",
  "impact": "<1-2 sentences on Impact on BESS>",
  "suggested_action": "<concrete internal follow-up, or Monitor only>"
}
"""

_BESS_STORY_FIELDS = [
    "takeaway",
    "impact",
    "suggested_action",
    "entity",
    "date",
    "url",
    "signal",
    "relevance",
]

JP_STORAGE_SUMMARY_PROFILE = build_base_summary_profile(
    profile_id="jp_storage_summary",
    system_prompt=SUMMARY_SYSTEM_PROMPT,
    narrative_field="executive_summary",
    narrative_label="Executive Summary",
    fallback_narrative=(
        "Automated LLM synthesis unavailable. See categorized stories below, "
        "scored for Japan BESS / energy storage relevance."
    ),
    default_watchlist=[
        "Monitor METI/ANRE capacity market and long-term auction updates",
        "Track JERA Cross and utility storage project COD announcements",
        "Watch trading company and battery OEM partnership / order news",
    ],
    story_fields=_BESS_STORY_FIELDS,
    replace_sections=[
        SummarySection(
            id="executive_summary",
            title="Executive Summary",
            kind="narrative",
            narrative_field="executive_summary",
        ),
        SummarySection(
            id="policy",
            title="Key Policy Updates",
            kind="grouped_stories",
            category_ids=["policy", "policy_market"],
            max_items=5,
            item_fields=list(_BESS_STORY_FIELDS),
        ),
        SummarySection(
            id="occto_grid",
            title="OCCTO / Grid Updates",
            kind="grouped_stories",
            category_ids=["occto_grid"],
            max_items=5,
            item_fields=list(_BESS_STORY_FIELDS),
        ),
        SummarySection(
            id="market_rules",
            title="Market Rule Changes",
            kind="grouped_stories",
            category_ids=["market_rules"],
            max_items=5,
            item_fields=list(_BESS_STORY_FIELDS),
        ),
        SummarySection(
            id="competitors",
            title="Competitor Movements",
            kind="grouped_stories",
            category_ids=[
                "competitors",
                "project_deployment",
                "corporate_activity",
                "technology_supply_chain",
            ],
            max_items=5,
            item_fields=list(_BESS_STORY_FIELDS),
        ),
        SummarySection(
            id="financing_ma",
            title="Financing / M&A / Platform Activity",
            kind="grouped_stories",
            category_ids=["financing_ma", "financing"],
            max_items=5,
            item_fields=list(_BESS_STORY_FIELDS),
        ),
        SummarySection(
            id="watchlist",
            title="Recommended Follow-ups / Watchlist",
            kind="watchlist",
        ),
        SummarySection(
            id="citations",
            title="Source Citations",
            kind="citations",
            max_items=10,
            max_items_docx=15,
        ),
    ],
)
JP_STORAGE_SUMMARY_PROFILE.category_section_map = {
    "policy": "policy",
    "policy_market": "policy",
    "occto_grid": "occto_grid",
    "market_rules": "market_rules",
    "competitors": "competitors",
    "project_deployment": "competitors",
    "corporate_activity": "competitors",
    "technology_supply_chain": "competitors",
    "financing_ma": "financing_ma",
    "financing": "financing_ma",
}

def _html(
    id: str,
    name: str,
    url: str,
    *,
    extra_urls: list[str] | None = None,
    languages: list[str] | None = None,
    link_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    allowed_domains: list[str] | None = None,
    allow_http_statuses: list[int] | None = None,
    priority_tier: int = 2,
    url_year_templated: bool = False,
    allow_pdf: bool = False,
) -> SourceConfig:
    return SourceConfig(
        id=id,
        name=name,
        kind="html",
        url=url,
        extra_urls=extra_urls or [],
        languages=languages or ["ja"],
        link_patterns=link_patterns or [],
        exclude_patterns=(exclude_patterns or []) + _COMMON_EXCLUDES,
        allowed_domains=allowed_domains or [],
        allow_http_statuses=allow_http_statuses or [],
        priority_tier=priority_tier,
        url_year_templated=url_year_templated,
        allow_pdf=allow_pdf,
    )


def _rss(
    id: str,
    name: str,
    url: str,
    *,
    languages: list[str] | None = None,
    link_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    priority_tier: int = 2,
) -> SourceConfig:
    return SourceConfig(
        id=id,
        name=name,
        kind="rss",
        url=url,
        languages=languages or ["ja"],
        link_patterns=link_patterns or [],
        exclude_patterns=exclude_patterns or [],
        priority_tier=priority_tier,
    )


def _sumitomo_archive(
    id: str,
    name: str,
    url: str,
    *,
    link_patterns: list[str],
    priority_tier: int = 2,
) -> SourceConfig:
    return SourceConfig(
        id=id,
        name=name,
        kind="sumitomo_archive",
        url=url,
        languages=["ja"],
        link_patterns=link_patterns,
        exclude_patterns=_COMMON_EXCLUDES,
        priority_tier=priority_tier,
        url_year_templated=True,
    )


SOURCES: list[SourceConfig] = [
    # Government — tier 4
    _html(
        "anre_news_release",
        "ANRE/METI (Energy & Environment Press, JA)",
        "https://www.meti.go.jp/press/category_05.html",
        languages=["ja"],
        link_patterns=["/press/"],
        priority_tier=4,
    ),
    _html(
        "meti_energy_press_en",
        "METI (Energy & Environment Press, EN)",
        "https://www.meti.go.jp/english/press/category_05.html",
        languages=["en"],
        link_patterns=["/english/press/", "category_05"],
        priority_tier=4,
    ),
    _rss(
        "occto_rss",
        "OCCTO (News RSS)",
        "https://www.occto.or.jp/news/feed.xml",
        languages=["ja"],
        link_patterns=["/news/", "/iinkai/", "/houkokusho/", "/iken/"],
        priority_tier=4,
    ),
    _html(
        "occto_news",
        "OCCTO (News)",
        "https://www.occto.or.jp/",
        languages=["ja"],
        link_patterns=["/news/"],
        exclude_patterns=["/iinkai/", "/nyusatsu/", "/iken/"],
        allow_http_statuses=[404],
        priority_tier=4,
    ),
    # Trading companies — tier 2
    _html(
        "mitsubishi_corp_release",
        "Mitsubishi Corp (News Release)",
        "https://www.mitsubishicorp.com/jp/ja/news/release/",
        languages=["ja"],
        link_patterns=["/news/release/"],
        priority_tier=2,
    ),
    _html(
        "mitsui_release",
        "Mitsui (Release)",
        "https://www.mitsui.com/jp/ja/release/{year}/index.html",
        languages=["ja"],
        link_patterns=["/release/"],
        url_year_templated=True,
        priority_tier=2,
    ),
    _html(
        "mitsui_topics",
        "Mitsui (Topics)",
        "https://www.mitsui.com/jp/ja/topics/{year}/index.html",
        languages=["ja"],
        link_patterns=["/topics/"],
        url_year_templated=True,
        priority_tier=2,
    ),
    _html(
        "mitsui_news",
        "Mitsui (What's New)",
        "https://www.mitsui.com/jp/ja/news/index.html",
        languages=["ja"],
        link_patterns=["/news/"],
        priority_tier=2,
    ),
    _rss(
        "itochu_press",
        "Itochu (Press Release)",
        "https://www.itochu.co.jp/ja/news/press/index.xml",
        languages=["ja"],
        link_patterns=["/news/press/"],
        exclude_patterns=["/ja/ir/", ".pdf"],
        priority_tier=2,
    ),
    _html(
        "itochu_chemical",
        "Itochu (Energy & Chemical)",
        "https://www.itochu.co.jp/ja/news/chemical/index.html",
        languages=["ja"],
        link_patterns=["/news/chemical/"],
        priority_tier=2,
    ),
    _sumitomo_archive(
        "sumitomo_release",
        "Sumitomo Corp (Release)",
        "https://www.sumitomocorp.com/ja/jp/news/release/{year}",
        link_patterns=["/news/release/"],
        priority_tier=2,
    ),
    _html(
        "sumitomo_group",
        "Sumitomo Corp (Group News)",
        "https://www.sumitomocorp.com/ja/jp/news/group/{year}",
        languages=["ja"],
        link_patterns=["/news/group/"],
        url_year_templated=True,
        priority_tier=2,
    ),
    _sumitomo_archive(
        "sumitomo_topics",
        "Sumitomo Corp (Topics)",
        "https://www.sumitomocorp.com/ja/jp/news/topics/{year}",
        link_patterns=["/news/topics/"],
        priority_tier=2,
    ),
    _html(
        "marubeni_news",
        "Marubeni (News)",
        "https://www.marubeni.com/jp/news/",
        languages=["ja"],
        link_patterns=["/jp/news/"],
        priority_tier=2,
    ),
    _html(
        "sojitz_release",
        "Sojitz (News Release)",
        "https://www.sojitz.com/jp/news/list/{year}/news-release/",
        languages=["ja"],
        link_patterns=["/news-release/", "/news/list/"],
        url_year_templated=True,
        priority_tier=2,
    ),
    _html(
        "sojitz_topics",
        "Sojitz (Topics)",
        "https://www.sojitz.com/jp/news/list/{year}/topics/",
        languages=["ja"],
        link_patterns=["/topics/", "/news/list/"],
        url_year_templated=True,
        priority_tier=2,
    ),
    _html(
        "toyota_tsusho_press",
        "Toyota Tsusho (Press)",
        "https://www.toyota-tsusho.com/press/",
        languages=["ja"],
        link_patterns=["/press/"],
        priority_tier=2,
    ),
    # Power companies — tier 3
    _html(
        "jera_information",
        "JERA (Information)",
        "https://www.jera.co.jp/news/information/{year}",
        languages=["ja"],
        link_patterns=["/news/information/"],
        url_year_templated=True,
        priority_tier=3,
    ),
    _html(
        "jera_notice",
        "JERA (Notices)",
        "https://www.jera.co.jp/news/notice/{year}",
        languages=["ja"],
        link_patterns=["/news/notice/"],
        url_year_templated=True,
        priority_tier=3,
    ),
    _html(
        "jera_cross_news",
        "JERA Cross (Storage Operations)",
        "https://www.jera-cross.com/ja/news/",
        languages=["ja"],
        link_patterns=["/news/"],
        priority_tier=3,
    ),
    _html(
        "tepco_release",
        "TEPCO (Press Release)",
        "https://www.tepco.co.jp/press/release/index-j.html",
        languages=["ja"],
        link_patterns=["/press/release/"],
        allow_pdf=True,
        priority_tier=3,
    ),
    _html(
        "tepco_notice",
        "TEPCO (Notices)",
        "https://www.tepco.co.jp/press/news/index-j.html",
        languages=["ja"],
        link_patterns=["/press/news/"],
        allow_pdf=True,
        priority_tier=3,
    ),
    _html(
        "chuden_press",
        "Chubu Electric (Press)",
        "https://www.chuden.co.jp/publicity/press/",
        languages=["ja"],
        link_patterns=["/publicity/press/"],
        priority_tier=3,
    ),
    _html(
        "kepco_pr",
        "Kansai Electric (PR)",
        "https://www.kepco.co.jp/corporate/pr/",
        languages=["ja"],
        link_patterns=["/corporate/pr/"],
        priority_tier=3,
    ),
    _html(
        "kepco_notice",
        "Kansai Electric (Notices)",
        "https://www.kepco.co.jp/corporate/notice/",
        languages=["ja"],
        link_patterns=["/corporate/notice/"],
        priority_tier=3,
    ),
    # Battery / storage manufacturers — tier 2
    _html(
        "gs_yuasa_release",
        "GS Yuasa (News Release)",
        "https://newsroom.gs-yuasa.com/news-release",
        languages=["ja"],
        link_patterns=["/news-release", "/news/"],
        priority_tier=2,
    ),
    _html(
        "gs_yuasa_topics",
        "GS Yuasa (Topics)",
        "https://newsroom.gs-yuasa.com/topics",
        languages=["ja"],
        link_patterns=["/topics"],
        priority_tier=2,
    ),
    _html(
        "toshiba_corporate_news",
        "Toshiba (Corporate News)",
        "https://www.global.toshiba/jp/news/corporate.html",
        languages=["ja"],
        link_patterns=["/news/"],
        priority_tier=2,
    ),
    _html(
        "toshiba_renewable_news",
        "Toshiba (Renewable Energy / VPP)",
        "https://www.global.toshiba/jp/products-solutions/renewable-energy/news.html",
        languages=["ja"],
        link_patterns=["/renewable-energy/", "/news"],
        priority_tier=2,
    ),
    _rss(
        "panasonic_energy_news",
        "Panasonic Energy (News)",
        "https://www.panasonic.com/content/dam/panasonic/jp/ja/energy/news/news_jp.xml",
        languages=["ja"],
        link_patterns=["news.panasonic.com/jp/"],
        priority_tier=2,
    ),
    _html(
        "hitachi_energy_press",
        "Hitachi Energy (Press Releases)",
        "https://www.hitachienergy.com/jp/ja/news-and-events/press-releases",
        languages=["ja", "en"],
        link_patterns=["/press-releases", "/news-and-events/"],
        priority_tier=2,
    ),
    _html(
        "hitachi_power_solutions_press",
        "Hitachi Power Solutions (News)",
        "https://www.hitachi-power-solutions.com/topics/news/index.html",
        languages=["ja"],
        link_patterns=[
            "/press/articles/",
            "/New/cnews/month/",
            "/corporate/news/",
        ],
        allowed_domains=[
            "www.hitachi.com",
            "www.hitachi.co.jp",
            "www.hitachi-solutions-tech.co.jp",
        ],
        priority_tier=2,
    ),
]

SOURCE_LABELS = {s.id: s.name for s in SOURCES}

PROFILE = TrackerProfile(
    id="jp_storage",
    name="Japan Energy Storage Ecosystem",
    # 政策、并网和项目公告频率较低，默认回看两周，避免周度运行漏报。
    default_recency_hours=14 * 24,
    keyword_tiers={
        "policy": _POLICY_KEYWORDS,
        "project": _PROJECT_KEYWORDS,
        "company": _COMPANY_KEYWORDS,
        "general": _POLICY_KEYWORDS + _PROJECT_KEYWORDS + _COMPANY_KEYWORDS,
    },
    sources=SOURCES,
    scoring_system_prompt=SCORING_SYSTEM_PROMPT,
    scoring_schema=ScoringSchema(
        category_options=[
            "policy_market",
            "project_deployment",
            "corporate_activity",
            "technology_supply_chain",
            "financing",
            "other",
        ],
        signal_options=["positive", "negative", "neutral", "n/a"],
    ),
    summary_system_prompt=SUMMARY_SYSTEM_PROMPT,
    summary_profile=JP_STORAGE_SUMMARY_PROFILE,
    analysis_system_prompt=ANALYSIS_SYSTEM_PROMPT,
    analysis_schema=AnalysisSchema(
        category_options=[
            "policy",
            "occto_grid",
            "market_rules",
            "competitors",
            "financing_ma",
            "other",
        ],
    ),
    noisy_source_ids=frozenset(),
    report_labels=ReportLabels(
        report_title="Japan BESS Weekly Intelligence Memo",
        filename_prefix="jp_storage_summary",
        sources_line=(
            "ANRE, METI, OCCTO, trading companies, power utilities, "
            "and storage/battery manufacturers"
        ),
        market_read_label="Executive Summary",
        why_it_matters_label="Why it matters",
        category_label="Category",
        signal_label="Signal",
        impact_label="Impact on BESS",
        suggested_action_label="Suggested Action",
        entity_label="Entity",
        signal_display={
            "positive": "Positive",
            "negative": "Negative",
            "neutral": "Neutral",
            "n/a": "N/A",
        },
        default_watchlist=list(JP_STORAGE_SUMMARY_PROFILE.default_watchlist),
        source_labels=SOURCE_LABELS,
        fallback_market_read=JP_STORAGE_SUMMARY_PROFILE.fallback_narrative,
    ),
    title_fallback_rules=[],
    boilerplate_terms=["breaking", "update", "live", "analysis"],
    high_priority_tiers=frozenset({"policy"}),
)
