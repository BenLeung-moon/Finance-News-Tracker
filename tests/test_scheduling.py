from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from finance_news_tracker.scheduling import should_run_today

HK = ZoneInfo("Asia/Hong_Kong")


def test_should_run_today_weekday():
    # 2026-06-03 is a Wednesday
    fake = datetime(2026, 6, 3, 10, 0, tzinfo=HK)
    with patch("finance_news_tracker.scheduling.datetime") as mock_dt:
        mock_dt.now.return_value = fake
        assert should_run_today(True, "Asia/Hong_Kong") is True


def test_should_run_today_saturday():
    fake = datetime(2026, 6, 6, 10, 0, tzinfo=HK)
    with patch("finance_news_tracker.scheduling.datetime") as mock_dt:
        mock_dt.now.return_value = fake
        assert should_run_today(True, "Asia/Hong_Kong") is False


def test_should_run_today_sunday():
    fake = datetime(2026, 6, 7, 10, 0, tzinfo=HK)
    with patch("finance_news_tracker.scheduling.datetime") as mock_dt:
        mock_dt.now.return_value = fake
        assert should_run_today(True, "Asia/Hong_Kong") is False


def test_should_run_today_disabled():
    fake = datetime(2026, 6, 7, 10, 0, tzinfo=HK)
    with patch("finance_news_tracker.scheduling.datetime") as mock_dt:
        mock_dt.now.return_value = fake
        assert should_run_today(False, "Asia/Hong_Kong") is True
