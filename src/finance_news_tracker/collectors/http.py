from __future__ import annotations

from finance_news_tracker.config import Settings


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


def browser_headers(settings: Settings) -> dict[str, str]:
    """Return browser-like headers for sites that reject script-looking requests.

    中文注解：部分日本政府/企业站点不只检查 User-Agent，还检查 Accept、
    Accept-Language 和 Sec-Fetch 系列请求头；集中生成可以避免各 collector
    行为不一致。
    """

    configured_user_agent = (settings.user_agent or "").strip()
    user_agent = (
        BROWSER_USER_AGENT
        if configured_user_agent.startswith("FinanceNewsTracker/")
        else configured_user_agent or BROWSER_USER_AGENT
    )
    return {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
