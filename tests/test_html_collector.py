from bs4 import BeautifulSoup

from finance_news_tracker.collectors.html import _extract_from_page
from finance_news_tracker.profiles.base import SourceConfig


def test_generic_html_extractor_respects_link_patterns():
    source = SourceConfig(
        id="test_source",
        name="Test",
        kind="html",
        url="https://example.com/news/",
        link_patterns=["/news/2026/"],
        exclude_patterns=["/tags/"],
        languages=["ja"],
    )
    html = """
    <html><body>
      <a href="/news/2026/001.html">蓄電池プロジェクトの商業運転を開始</a>
      <a href="/tags/storage/">タグ一覧</a>
      <a href="/about/">会社概要</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_from_page(soup, source, "https://example.com/news/")
    assert len(items) == 1
    assert "蓄電池" in items[0].title
    assert "/news/2026/001.html" in items[0].url


def test_html_extractor_parses_time_datetime():
    source = SourceConfig(
        id="test_time",
        name="Test Time",
        kind="html",
        url="https://example.com/press/",
        link_patterns=["/press/"],
        languages=["en"],
    )
    html = """
    <html><body>
      <article>
        <time datetime="2026-03-25"></time>
        <a href="/press/2026/storage-deal.html">New BESS project financing announced</a>
      </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_from_page(soup, source, "https://example.com/press/")
    assert len(items) == 1
    assert items[0].published_at is not None
    assert items[0].published_at.year == 2026
