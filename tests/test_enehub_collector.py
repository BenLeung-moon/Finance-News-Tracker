from bs4 import BeautifulSoup

from finance_news_tracker.collectors.enehub import (
    _extract_article_body,
    _extract_list_items,
    _page_url,
)
from finance_news_tracker.profiles.base import SourceConfig


def _source() -> SourceConfig:
    return SourceConfig(
        id="enehub_jp",
        name="エネハブ (News)",
        kind="enehub",
        url="https://enehub.jp/news/",
        languages=["ja"],
        link_patterns=["/news/"],
        exclude_patterns=["?e-page-"],
    )


def test_extract_list_items_uses_primary_loop_and_deduplicates_urls():
    html = """
    <div class="elementor-element-2cc0520">
      <div class="e-loop-item">
        <a href="https://enehub.jp/news/bess-project/">系統用蓄電所の運用を開始</a>
        <time>2026年7月17日</time>
      </div>
      <div class="e-loop-item">
        <a href="https://enehub.jp/news/bess-project/">系統用蓄電所の運用を開始</a>
        <time>2026年7月17日</time>
      </div>
    </div>
    <div class="related-posts">
      <a href="https://enehub.jp/news/old-story/">関連ニュース記事</a>
    </div>
    """

    items = _extract_list_items(BeautifulSoup(html, "lxml"), _source())

    assert len(items) == 1
    assert items[0][0] == "系統用蓄電所の運用を開始"
    assert items[0][1] == "https://enehub.jp/news/bess-project/"
    assert items[0][2].isoformat() == "2026-07-17T00:00:00+00:00"


def test_extract_list_items_skips_cards_without_a_date():
    html = """
    <div class="elementor-element-2cc0520">
      <div class="e-loop-item">
        <a href="https://enehub.jp/news/undated/">日付がないニュース</a>
      </div>
    </div>
    """

    assert _extract_list_items(BeautifulSoup(html, "lxml"), _source()) == []


def test_page_url_preserves_query_and_sets_elementor_page():
    url = _page_url("https://enehub.jp/news/?source=tracker", 3)

    assert "source=tracker" in url
    assert "e-page-2cc0520=3" in url


def test_extract_article_body_excludes_page_chrome():
    html = """
    <header>エネハブ</header>
    <div class="elementor-widget-theme-post-content">
      <p>蓄電所を新設します。</p><p>運転開始は2026年です。</p>
    </div>
    <footer>利用規約</footer>
    """

    assert _extract_article_body(html) == "蓄電所を新設します。 運転開始は2026年です。"
