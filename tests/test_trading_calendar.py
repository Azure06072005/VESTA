"""tests/test_trading_calendar.py

Kiểm thử tự động logic lịch giao dịch và quy chuẩn ngắt cào OHLCV vào cuối tuần và lễ tết.
"""
import datetime as dt
import pathlib
import sys
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from crawlers.trading_calendar import (
    get_market_status,
    is_exchange_holiday,
    is_trading_day,
    is_weekend,
    should_skip_ohlcv_crawl,
)


def test_weekend_detection():
    # 2026-10-10 là Thứ Bảy, 2026-10-11 là Chủ Nhật
    sat = dt.date(2026, 10, 10)
    sun = dt.date(2026, 10, 11)
    mon = dt.date(2026, 10, 12)

    assert is_weekend(sat) is True
    assert is_weekend(sun) is True
    assert is_weekend(mon) is False

    assert is_trading_day(sat) is False
    assert is_trading_day(sun) is False
    assert is_trading_day(mon) is True


def test_should_skip_ohlcv_on_weekends():
    sat = dt.date(2026, 10, 10)
    skip, reason = should_skip_ohlcv_crawl(sat)
    assert skip is True
    assert "Thứ Bảy" in reason or "cuối tuần" in reason

    sun = dt.date(2026, 10, 11)
    skip, reason = should_skip_ohlcv_crawl(sun)
    assert skip is True
    assert "Chủ Nhật" in reason or "cuối tuần" in reason


def test_should_skip_ohlcv_on_holidays():
    # 30/4/2026 là Thứ Năm
    holiday_30_4 = dt.date(2026, 4, 30)
    assert is_weekend(holiday_30_4) is False
    assert is_exchange_holiday(holiday_30_4) is True
    assert is_trading_day(holiday_30_4) is False

    skip, reason = should_skip_ohlcv_crawl(holiday_30_4)
    assert skip is True
    assert "Nghỉ Lễ" in reason

    # 02/09/2026 là Quốc khánh
    national_day = dt.date(2026, 9, 2)
    assert is_trading_day(national_day) is False
    skip, reason = should_skip_ohlcv_crawl(national_day)
    assert skip is True


def test_normal_trading_day_allows_ohlcv():
    # 2026-10-14 là Thứ Tư làm việc bình thường
    wed = dt.date(2026, 10, 14)
    assert is_weekend(wed) is False
    assert is_exchange_holiday(wed) is False
    assert is_trading_day(wed) is True

    skip, reason = should_skip_ohlcv_crawl(wed)
    assert skip is False


def test_market_status_payload():
    sat = dt.date(2026, 10, 10)
    status = get_market_status(sat)
    assert status["is_trading_day"] is False
    assert status["can_crawl_ohlcv"] is False
    assert status["can_crawl_indices"] is False
    assert status["can_crawl_news"] is True  # Tin tức luôn luôn được phép cào!


def test_force_override():
    sat = dt.date(2026, 10, 10)
    skip, reason = should_skip_ohlcv_crawl(sat, force=True)
    assert skip is False
    assert "FORCE_ENABLED" in reason
