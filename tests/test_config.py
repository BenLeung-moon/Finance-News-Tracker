from finance_news_tracker.config import parse_email_recipients


def test_parse_email_recipients_single():
    assert parse_email_recipients("a@example.com") == ["a@example.com"]


def test_parse_email_recipients_multiple():
    assert parse_email_recipients(
        "a@example.com, b@example.com ,c@example.com"
    ) == ["a@example.com", "b@example.com", "c@example.com"]


def test_parse_email_recipients_empty():
    assert parse_email_recipients("") == []
