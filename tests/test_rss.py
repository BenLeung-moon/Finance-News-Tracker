from finance_news_tracker.collectors.rss import _strip_html


def test_strip_html_removes_tags():
    raw = "<p>USD/JPY <strong>rises</strong> on Fed remarks.</p>"
    assert _strip_html(raw) == "USD/JPY rises on Fed remarks."


def test_strip_html_plain_text_unchanged():
    assert _strip_html("Plain headline only") == "Plain headline only"
