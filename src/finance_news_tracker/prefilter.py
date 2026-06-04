from __future__ import annotations



import re

from datetime import datetime, timezone



from finance_news_tracker.config import Settings

from finance_news_tracker.dedupe import (

    FX_MEDIA_SOURCES,

    apply_source_quotas,

    dedupe_articles,

    is_fx_media_source,

)

from finance_news_tracker.models import Article, ScoredArticle



# Direct USD/JPY / Japan channel evidence for stricter FX-media prefilter

MEDIA_DIRECT_KEYWORDS: list[str] = [

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



# Strong macro terms (need >=2 for media pass without direct USD/JPY hit)

MEDIA_STRONG_MACRO_KEYWORDS: list[str] = [

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



# Weak alone — generic forex headlines that crowd the feed

MEDIA_WEAK_ONLY_KEYWORDS: list[str] = [

    "forex",

    "fx",

    "currency",

    "dollar",

    "exchange rate",

    "rate",

    "rates",

]





def keyword_hits(text: str, keywords: list[str]) -> list[str]:

    lower = text.lower()

    hits = []

    for kw in keywords:

        if kw.lower() in lower:

            hits.append(kw)

    return hits





def _media_prefilter(blob: str, settings: Settings) -> tuple[bool, list[str]]:

    """Stricter gate for FXStreet / Investing.com — reduce generic FX noise."""

    direct = keyword_hits(blob, MEDIA_DIRECT_KEYWORDS)

    if direct:

        return True, direct



    strong = keyword_hits(blob, MEDIA_STRONG_MACRO_KEYWORDS)

    if len(strong) >= 2:

        return True, strong



    all_hits = keyword_hits(blob, settings.fx_keywords)

    weak_only = keyword_hits(blob, MEDIA_WEAK_ONLY_KEYWORDS)

    if all_hits and not weak_only:

        return True, all_hits

    if all_hits and len(all_hits) > len(weak_only):

        non_weak = [h for h in all_hits if h not in MEDIA_WEAK_ONLY_KEYWORDS]

        if non_weak:

            return True, non_weak



    return False, []





def prefilter_article(article: Article, settings: Settings) -> tuple[bool, list[str]]:

    blob = " ".join(

        filter(

            None,

            [article.title, article.summary, article.raw_excerpt],

        )

    )



    if is_fx_media_source(article.source):

        return _media_prefilter(blob, settings)



    hits = keyword_hits(blob, settings.fx_keywords)

    if hits:

        return True, hits



    # BOJ / macro titles often lack explicit FX terms

    if article.source.startswith("boj"):

        macro_terms = re.compile(

            r"monetary|policy|rate|inflation|cpi|bond|yen|dollar|fx|exchange|"

            r"intervention|statement|mpm|tankan|outlook",

            re.IGNORECASE,

        )

        if macro_terms.search(article.title):

            return True, ["boj_macro"]



    # Fed / Treasury official releases often use formal titles without FX jargon

    if article.source.startswith("fed_"):

        fed_terms = re.compile(

            r"monetary|policy|rate|inflation|cpi|fomc|powell|speech|testimony|"

            r"statement|minutes|funds|yield|financial|supervision",

            re.IGNORECASE,

        )

        if fed_terms.search(article.title):

            return True, ["fed_macro"]



    if article.source.startswith("us_treasury_"):

        treasury_terms = re.compile(

            r"treasury|fiscal|debt|refunding|tic|capital|yield|auction|"

            r"secretary|sanction|tariff|inflation|economic",

            re.IGNORECASE,

        )

        if treasury_terms.search(article.title):

            return True, ["us_treasury_macro"]



    return False, []





def _priority_for_article(article: Article, hit: bool, hits: list[str]) -> int:

    priority = len(hits)

    if article.source.startswith("boj"):

        priority += 3

    if article.source.startswith("fed_"):

        priority += 3

    if article.source.startswith("us_treasury_"):

        priority += 3

    if hit:

        priority += 2

    # Deprioritize generic media relative to official sources

    if is_fx_media_source(article.source):

        priority = max(0, priority - 1)

    return priority





def rank_for_scoring(

    articles: list[tuple[Article, int]],

    settings: Settings,

) -> list[tuple[Article, int]]:

    """Return articles prioritized for DeepSeek scoring."""



    scored: list[tuple[Article, int, int, list[str]]] = []

    for article, article_id in articles:

        hit, hits = prefilter_article(article, settings)

        if is_fx_media_source(article.source) and not hit:

            continue

        priority = _priority_for_article(article, hit, hits)

        scored.append((article, article_id, priority, hits))



    now = datetime.now(timezone.utc)



    def _sort_key(item: tuple[Article, int, int, list[str]]) -> tuple[int, datetime]:

        article = item[0]

        pub = article.published_at

        if pub is None:

            pub = now

        elif pub.tzinfo is None:

            pub = pub.replace(tzinfo=timezone.utc)

        return (item[2], pub)



    scored.sort(key=_sort_key, reverse=True)



    ranked_triples = [(a, aid, pri) for a, aid, pri, _ in scored]

    deduped = dedupe_articles(ranked_triples, settings.dedupe_similarity_threshold)



    per_source_limits = {

        src: settings.fx_media_score_limit_per_source for src in FX_MEDIA_SOURCES

    }

    limited = apply_source_quotas(

        deduped,

        per_source_limits=per_source_limits,

        combined_media_limit=settings.fx_media_score_limit_combined,

        max_total=settings.max_articles_to_score,

    )

    return limited





def build_scored_articles(

    articles: list[tuple[Article, int]],

    settings: Settings,

) -> list[ScoredArticle]:

    result: list[ScoredArticle] = []

    for article, article_id in articles:

        hit, hits = prefilter_article(article, settings)

        result.append(

            ScoredArticle(

                article=article,

                article_id=article_id,

                prefilter_hit=hit,

                keyword_hits=hits,

            )

        )

    return result


