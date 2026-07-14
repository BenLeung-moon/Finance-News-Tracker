from finance_news_tracker.collectors.rss import _entry_allowed, _strip_html
from finance_news_tracker.profiles.base import SourceConfig


def test_strip_html_removes_tags():
    raw = "<p>USD/JPY <strong>rises</strong> on Fed remarks.</p>"
    assert _strip_html(raw) == "USD/JPY rises on Fed remarks."


def test_strip_html_plain_text_unchanged():
    assert _strip_html("Plain headline only") == "Plain headline only"


def test_rss_entry_allowed_respects_patterns_and_excludes():
    source = SourceConfig(
        id="itochu_press",
        name="Itochu Press",
        kind="rss",
        url="https://www.itochu.co.jp/ja/news/press/index.xml",
        link_patterns=["/news/press/"],
        exclude_patterns=["/ja/ir/", ".pdf"],
    )

    assert _entry_allowed(
        source,
        "[エネルギー・化学品] 系統用蓄電所事業の共同推進について",
        "https://www.itochu.co.jp/ja/news/press/2026/260601.html",
    )
    assert not _entry_allowed(
        source,
        "[適時開示] 決算公表",
        "https://www.itochu.co.jp/ja/ir/financial_statements/2026/index.html",
    )
    assert not _entry_allowed(
        source,
        "[その他] 人事異動について（PDF）",
        "https://www.itochu.co.jp/ja/news/press/2026/news_260610.pdf",
    )
