from __future__ import annotations

import re
from datetime import datetime, timezone

from finance_news_tracker.config import Settings
from finance_news_tracker.models import Article, ScoredArticle


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    hits = []
    for kw in keywords:
        if kw.lower() in lower:
            hits.append(kw)
    return hits


def prefilter_article(article: Article, settings: Settings) -> tuple[bool, list[str]]:
    blob = " ".join(
        filter(
            None,
            [article.title, article.summary, article.raw_excerpt],
        )
    )
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

    return False, []


def rank_for_scoring(
    articles: list[tuple[Article, int]],
    settings: Settings,
) -> list[tuple[Article, int]]:
    """Return articles prioritized for DeepSeek scoring."""

    scored: list[tuple[Article, int, int, list[str]]] = []
    for article, article_id in articles:
        hit, hits = prefilter_article(article, settings)
        priority = len(hits)
        if article.source.startswith("boj"):
            priority += 3
        if hit:
            priority += 2
        scored.append((article, article_id, priority, hits))

    now = datetime.now(timezone.utc)

    def _sort_key(item: tuple[Article, int, int, list[str]]) -> tuple[int, datetime]:
        article = item[0]
        pub = article.published_at
        if pub is None:
            # Undated (e.g. Nikkei RSS) is treated as just-seen, not oldest.
            pub = now
        elif pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return (item[2], pub)

    scored.sort(key=_sort_key, reverse=True)

    limited = scored[: settings.max_articles_to_score]
    return [(a, aid) for a, aid, _, _ in limited]


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
