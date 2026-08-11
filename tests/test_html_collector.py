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


def test_html_extractor_allows_configured_external_domains():
    source = SourceConfig(
        id="hitachi_test",
        name="Hitachi Test",
        kind="html",
        url="https://www.hitachi-power-solutions.com/topics/news/index.html",
        link_patterns=["/New/cnews/month/"],
        allowed_domains=["www.hitachi.co.jp"],
        languages=["ja"],
    )
    html = """
    <html><body>
      <a href="https://www.hitachi.co.jp/New/cnews/month/2025/11/1127.html">
        日立と日立パワーソリューションズがマイクログリッドを融合したモデル構築に着手
      </a>
      <a href="https://unrelated.example.com/New/cnews/month/2025/11/1127.html">
        unrelated external article
      </a>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_from_page(
        soup,
        source,
        "https://www.hitachi-power-solutions.com/topics/news/index.html",
    )
    assert len(items) == 1
    assert items[0].url.startswith("https://www.hitachi.co.jp/")


def test_card_selector_extracts_clean_title_and_numeric_date():
    """Anonymous card-list fixture for title_selector + date_formats."""
    source = SourceConfig(
        id="card_news",
        name="Card News",
        kind="html",
        url="https://example.com/en/news/",
        languages=["en"],
        link_patterns=["/en/news/"],
        exclude_patterns=["index_"],
        title_selector="p.mc_e1_txt",
        date_selector="div.mc_e1_date",
        date_formats=["%m/%d/%Y"],
    )
    html = """
    <html><body>
      <ul>
        <li class="mc_e1_li">
          <a href="/en/news/6942.html" class="mc_e1_lisbox">
            <div class="mc_e1_txtbox">
              <p class="mc_e1_txt">Brunp Wins Two Honors at the European Inventor Award 2026</p>
              <div class="mc_e1_date">7/04/2026</div>
            </div>
          </a>
        </li>
        <li class="mc_e1_li">
          <a href="/en/news/index_2.html" class="mc_e1_lisbox">
            <p class="mc_e1_txt">Next page listing should be excluded</p>
            <div class="mc_e1_date">7/01/2026</div>
          </a>
        </li>
        <li class="mc_e1_li">
          <a href="/en/about/" class="mc_e1_lisbox">
            <p class="mc_e1_txt">About navigation link</p>
          </a>
        </li>
        <li class="mc_e1_li">
          <a href="/en/news/6942.html" class="mc_e1_lisbox">
            <p class="mc_e1_txt">Brunp Wins Two Honors at the European Inventor Award 2026</p>
            <div class="mc_e1_date">7/04/2026</div>
          </a>
        </li>
      </ul>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_from_page(soup, source, "https://example.com/en/news/")
    assert len(items) == 1
    assert items[0].title == "Brunp Wins Two Honors at the European Inventor Award 2026"
    assert items[0].url == "https://example.com/en/news/6942.html"
    assert items[0].source == "card_news"
    assert items[0].published_at is not None
    assert items[0].published_at.year == 2026
    assert items[0].published_at.month == 7
    assert items[0].published_at.day == 4


def test_card_selector_extracts_title_and_month_name_date():
    """Anonymous card-list fixture with month-name date formats and nested h1."""
    source = SourceConfig(
        id="newsroom_updates",
        name="Newsroom Updates",
        kind="html",
        url="https://example.com/newsroom/LatestUpdates",
        languages=["en"],
        link_patterns=["/newsroom/latest/details/"],
        title_selector="h1",
        date_selector="div.time",
        date_formats=["%B %d,%Y"],
    )
    html = """
    <html><body>
      <div class="new-list view">
        <a href="https://example.com/newsroom/latest/details/461.html">
          <div class="txt">
            <div class="time">July                                28,2026</div>
            <h1 class="h4-b t1">
              Vendor Supports Partner Expansion with First Project in Navarra
            </h1>
            <div class="vmore"><div class="mc">view details</div></div>
          </div>
        </a>
        <a href="https://example.com/newsroom/latest/details/446.html">
          <div class="txt">
            <div class="time">July                                02,2026</div>
            <h1 class="h2-s-b text-uppercase">
              Vendor Navarra Open Day: Cobuilding Spain's Local Industrial Ecosystem
            </h1>
          </div>
        </a>
        <a href="https://example.com/newsroom/LatestUpdates/2.html">
          <div class="txt">
            <div class="time">July 01,2026</div>
            <h1 class="h4-b t1">Pagination page should be excluded by link pattern</h1>
          </div>
        </a>
        <a href="https://example.com/newsroom/latest/details/461.html">
          <div class="txt">
            <div class="time">July 28,2026</div>
            <h1 class="h4-b t1">
              Vendor Supports Partner Expansion with First Project in Navarra
            </h1>
          </div>
        </a>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_from_page(
        soup, source, "https://example.com/newsroom/LatestUpdates"
    )
    assert len(items) == 2
    assert items[0].title.startswith("Vendor Supports Partner Expansion")
    assert "view details" not in items[0].title.lower()
    assert "July" not in items[0].title
    assert items[1].title.startswith("Vendor Navarra Open Day")
    assert items[0].url.endswith("/newsroom/latest/details/461.html")
    assert items[0].published_at is not None
    assert items[0].published_at.year == 2026
    assert items[0].published_at.month == 7
    assert items[0].published_at.day == 28


def test_html_extractor_does_not_invent_date_without_selectors():
    source = SourceConfig(
        id="undated_test",
        name="Undated",
        kind="html",
        url="https://example.com/news/",
        link_patterns=["/news/"],
        languages=["en"],
    )
    html = """
    <html><body>
      <a href="/news/evergreen-page.html">Evergreen corporate overview without a date</a>
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    items = _extract_from_page(soup, source, "https://example.com/news/")
    assert len(items) == 1
    assert items[0].published_at is None
