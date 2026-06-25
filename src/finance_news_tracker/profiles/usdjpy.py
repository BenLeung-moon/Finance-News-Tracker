"""USD/JPY profile — migrated from legacy hard-coded config; behavior unchanged."""

from __future__ import annotations

from finance_news_tracker.profiles.base import (
    ReportLabels,
    ScoringSchema,
    SourceConfig,
    TitleFallbackRule,
    TrackerProfile,
)

# --- Keywords (formerly config.FX_KEYWORDS + prefilter MEDIA_* lists) ---

GENERAL_KEYWORDS: list[str] = [
    "usd/jpy",
    "usd-jpy",
    "dollar-yen",
    "dollar yen",
    "usdjpy",
    "yen",
    "jpy",
    "boj",
    "bank of japan",
    "fed",
    "federal reserve",
    "rate",
    "rates",
    "interest rate",
    "monetary policy",
    "inflation",
    "cpi",
    "wage",
    "wages",
    "jgb",
    "bond",
    "treasury",
    "yield",
    "intervention",
    "mof",
    "finance ministry",
    "trade balance",
    "current account",
    "oil",
    "crude",
    "risk-off",
    "risk on",
    "carry trade",
    "fx",
    "forex",
    "exchange rate",
    "currency",
    "dollar",
    "gdp",
    "pmi",
    "tankan",
    "mpm",
    "statement on monetary policy",
    "fomc",
    "powell",
    "fed funds",
    "treasury yields",
    "tic",
    "treasury international capital",
    "quarterly refunding",
    "payrolls",
    "pce",
    "ppi",
    "retail sales",
    "ism",
    "tariff",
    "debt issuance",
    "fiscal",
]

DIRECT_KEYWORDS: list[str] = [
    "usd/jpy",
    "usd-jpy",
    "dollar-yen",
    "dollar yen",
    "usdjpy",
    "yen",
    "jpy",
    "boj",
    "bank of japan",
    "japan",
    "intervention",
    "mof",
    "finance ministry",
    "jgb",
    "tankan",
    "carry trade",
]

STRONG_KEYWORDS: list[str] = [
    "fed",
    "federal reserve",
    "fomc",
    "powell",
    "monetary policy",
    "interest rate",
    "inflation",
    "cpi",
    "pce",
    "payrolls",
    "yield",
    "treasury yields",
    "treasury",
    "rate decision",
    "rate hike",
    "rate cut",
    "risk-off",
    "risk on",
]

WEAK_KEYWORDS: list[str] = [
    "forex",
    "fx",
    "currency",
    "dollar",
    "exchange rate",
    "rate",
    "rates",
]

SCORING_SYSTEM_PROMPT = """You are a senior FX strategist analyzing financial news
(Japan, US policy, international FX) for relevance to USD/JPY (US dollar vs Japanese yen).

Score each article for how likely it is to move or inform USD/JPY trading in the near term.
This is explanatory relevance, not statistical correlation.

Respond with ONLY valid JSON (no markdown fences) matching this schema:
{
  "relevance_score": <integer 0-100>,
  "category": "<one of: monetary_policy, rates_differential, inflation, intervention, risk_sentiment, trade_commodities, growth_data, fiscal_policy, other>",
  "signal": "<one of: usd_jpy_up, usd_jpy_down, mixed, unclear>",
  "confidence": "<one of: low, medium, high>",
  "summary": "<2-3 sentence summary>",
  "why_it_matters": "<1-2 sentences on USD/JPY transmission mechanism>",
  "source_citation": "<title and source in one line>"
}

Scoring guide:
- 80-100: Direct BOJ/Fed policy, intervention, major CPI/rates surprise
- 60-79: Strong macro with clear yen channel (wages, JGB, oil shock to Japan)
- 40-59: Indirect but meaningful (trade, risk-off, fiscal)
- 20-39: Weak or tangential
- 0-19: Not relevant to USD/JPY
"""

SUMMARY_SYSTEM_PROMPT = """You are a senior FX strategist writing an executive summary for
USD/JPY traders based on scored financial news (Japan, US policy, and international FX media).

Write in clear English. Be concise and actionable. Do not claim statistical correlation;
frame insights as narrative relevance and market transmission. The per-article relevance
scores are provided to you as context; do not restate or invent numeric scores.

Respond with ONLY valid JSON (no markdown fences):
{
  "market_read": "<one paragraph overall USD/JPY read>",
  "watchlist": ["<upcoming event or risk 1>", "<event 2>", "..."]
}
"""

SOURCES: list[SourceConfig] = [
    SourceConfig(
        id="boj_whatsnew",
        name="Bank of Japan (What's New)",
        kind="rss",
        url="https://www.boj.or.jp/en/rss/whatsnew.xml",
        languages=["en"],
        priority_tier=4,
    ),
    SourceConfig(
        id="boj_statistics",
        name="Bank of Japan (Statistics)",
        kind="rss",
        url="https://www.boj.or.jp/en/rss/statistics.xml",
        languages=["en"],
        priority_tier=4,
    ),
    SourceConfig(
        id="nikkei_asia",
        name="Nikkei Asia",
        kind="rss",
        url="https://asia.nikkei.com/rss/feed/nar",
        languages=["en"],
        priority_tier=3,
    ),
    SourceConfig(
        id="nhk_world",
        name="NHK WORLD-JAPAN",
        kind="html",
        url="https://www3.nhk.or.jp/nhkworld/en/news/list/",
        extra_urls=[
            "https://www3.nhk.or.jp/nhkworld/en/news/tags/60/",
            "https://www3.nhk.or.jp/nhkworld/en/news/",
        ],
        languages=["en"],
        link_patterns=["/nhkworld/en/news/"],
        exclude_patterns=[
            "/backstories/",
            "/tags/",
            "/list/",
            "/video/",
            "/live_",
        ],
        priority_tier=3,
    ),
    SourceConfig(
        id="fed_press_monetary",
        name="Federal Reserve (Monetary Policy Press)",
        kind="rss",
        url="https://www.federalreserve.gov/feeds/press_monetary.xml",
        languages=["en"],
        priority_tier=4,
    ),
    SourceConfig(
        id="fed_speeches",
        name="Federal Reserve (Speeches)",
        kind="rss",
        url="https://www.federalreserve.gov/feeds/speeches.xml",
        languages=["en"],
        priority_tier=4,
    ),
    SourceConfig(
        id="us_treasury_press",
        name="US Treasury (Press Releases)",
        kind="html",
        url="https://home.treasury.gov/news/press-releases",
        languages=["en"],
        link_patterns=["/news/press-releases/sb"],
        priority_tier=4,
    ),
    SourceConfig(
        id="fxstreet_news",
        name="FXStreet (Forex News)",
        kind="rss",
        url="https://www.fxstreet.com/rss/news",
        languages=["en"],
        priority_tier=1,
        is_noisy=True,
    ),
    SourceConfig(
        id="investing_forex",
        name="Investing.com (Forex)",
        kind="rss",
        url="https://www.investing.com/rss/forex.rss",
        languages=["en"],
        priority_tier=1,
        is_noisy=True,
    ),
]

SOURCE_LABELS = {
    "boj_whatsnew": "Bank of Japan",
    "boj_statistics": "BOJ Statistics",
    "nikkei_asia": "Nikkei Asia",
    "nhk_world": "NHK WORLD-JAPAN",
    "fed_press_monetary": "Federal Reserve (Monetary Policy)",
    "fed_speeches": "Federal Reserve (Speeches)",
    "us_treasury_press": "US Treasury",
    "fxstreet_news": "FXStreet",
    "investing_forex": "Investing.com (Forex)",
}

PROFILE = TrackerProfile(
    id="usdjpy",
    name="USD/JPY Finance News",
    keyword_tiers={
        "general": GENERAL_KEYWORDS,
        "direct": DIRECT_KEYWORDS,
        "strong": STRONG_KEYWORDS,
        "weak": WEAK_KEYWORDS,
    },
    sources=SOURCES,
    scoring_system_prompt=SCORING_SYSTEM_PROMPT,
    scoring_schema=ScoringSchema(
        category_options=[
            "monetary_policy",
            "rates_differential",
            "inflation",
            "intervention",
            "risk_sentiment",
            "trade_commodities",
            "growth_data",
            "fiscal_policy",
            "other",
        ],
        signal_options=["usd_jpy_up", "usd_jpy_down", "mixed", "unclear"],
    ),
    summary_system_prompt=SUMMARY_SYSTEM_PROMPT,
    noisy_source_ids=frozenset({"fxstreet_news", "investing_forex"}),
    report_labels=ReportLabels(
        report_title="USD/JPY Executive Summary",
        filename_prefix="usdjpy_summary",
        sources_line=(
            "BOJ, Nikkei Asia, NHK, Federal Reserve, US Treasury, "
            "FXStreet, Investing.com"
        ),
        why_it_matters_label="Why USD/JPY",
        category_label="Channel",
        signal_label="Direction",
        signal_display={
            "usd_jpy_up": "USD/JPY ↑ (yen weaker)",
            "usd_jpy_down": "USD/JPY ↓ (yen stronger)",
            "mixed": "Mixed",
            "unclear": "Unclear",
            "usd_jpy_bullish": "Bullish USD/JPY",
            "usd_jpy_bearish": "Bearish USD/JPY",
        },
        default_watchlist=[
            "Monitor BOJ release calendar and upcoming MPM dates",
            "Watch US data (CPI, payrolls) for rate differential moves",
        ],
        source_labels=SOURCE_LABELS,
        fallback_market_read=(
            "Automated LLM synthesis unavailable. See ranked stories below, "
            "scored for USD/JPY relevance per article."
        ),
    ),
    title_fallback_rules=[
        TitleFallbackRule(
            source_prefix="boj",
            pattern=(
                r"monetary|policy|rate|inflation|cpi|bond|yen|dollar|fx|exchange|"
                r"intervention|statement|mpm|tankan|outlook"
            ),
            tag="boj_macro",
        ),
        TitleFallbackRule(
            source_prefix="fed_",
            pattern=(
                r"monetary|policy|rate|inflation|cpi|fomc|powell|speech|testimony|"
                r"statement|minutes|funds|yield|financial|supervision"
            ),
            tag="fed_macro",
        ),
        TitleFallbackRule(
            source_prefix="us_treasury_",
            pattern=(
                r"treasury|fiscal|debt|refunding|tic|capital|yield|auction|"
                r"secretary|sanction|tariff|inflation|economic"
            ),
            tag="us_treasury_macro",
        ),
    ],
    boilerplate_terms=["breaking", "update", "live", "analysis", "forex", "fx"],
    high_priority_tiers=frozenset({"direct"}),
)
