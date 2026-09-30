"""Unit and integration tests for src/crawlers/market_insights.py.

Kiểm thử toàn diện module Direct REST API thay thế vnstock_data (F007b):
- Vietcap IQ Direct API (Screener, Criteria).
- VNDIRECT FINFO Direct API (Rankings, Foreign Flows, Valuation Ratios).
- ASEAN Securities Research API (Breadth, Fear & Greed, Macroeconomic Indicators).
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from crawlers import market_insights
from etl.retry_failed_jobs import EmptyResultError


# ============================================================================
# 1. VIETCAP IQ DIRECT SCREENER TESTS
# ============================================================================

def test_fetch_market_screener_parsing():
    """Kiểm tra xử lý schema và chuyển đổi kiểu dữ liệu của Vietcap Screener."""
    mock_response_data = {
        "data": {
            "totalElements": 2,
            "content": [
                {
                    "id": 101,
                    "ticker": "FPT",
                    "exchange": "hsx",
                    "refPrice": 130.0,
                    "ceiling": 139.1,
                    "floor": 120.9,
                    "price": 135.5,
                    "pe": 22.4,
                    "pb": 5.1,
                    "roe": 28.5,
                    "rs3M": 85.0,
                    "priceChangePct1D": 2.5,
                    "volumeSpike20DPct": 125.0,
                },
                {
                    "id": 102,
                    "ticker": "VNM",
                    "exchange": "hsx",
                    "refPrice": 70.0,
                    "ceiling": 74.9,
                    "floor": 65.1,
                    "price": 69.5,
                    "pe": 16.2,
                    "pb": 3.8,
                    "roe": 24.1,
                    "rs3M": 45.0,
                    "priceChangePct1D": -0.7,
                    "volumeSpike20DPct": 80.0,
                }
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_market_screener()

    assert not df.empty
    assert len(df) == 2
    assert "id" not in df.columns
    assert "symbol" in df.columns
    assert df["symbol"].tolist() == ["FPT", "VNM"]
    assert "reference_price" in df.columns
    assert "ceiling_price" in df.columns
    assert "floor_price" in df.columns
    assert "price_change_percent" in df.columns
    assert "volume_spike_20d_percent" in df.columns
    assert df["pe"].dtype in ["float64", "float32"]
    assert df["roe"].iloc[0] == 28.5
    assert df.attrs["source"] == "VIETCAP_IQ_DIRECT"
    assert df.attrs["total_elements"] == 2


def test_fetch_market_screener_empty():
    """Kiểm tra phản hồi rỗng từ Vietcap IQ ném EmptyResultError."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"data": {"content": []}}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(EmptyResultError):
            market_insights.fetch_market_screener()


def test_fetch_screener_criteria():
    """Kiểm tra danh mục criteria từ Vietcap IQ."""
    mock_criteria = {
        "data": [
            {
                "category": "valuation",
                "name": "pe",
                "viName": "Chỉ số P/E",
                "enName": "P/E Ratio",
                "selectType": "range"
            },
            {
                "category": "technical",
                "name": "rsi",
                "viName": "Chỉ số RSI",
                "enName": "RSI Indicator",
                "selectType": "range"
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_criteria).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_screener_criteria(lang="vi")

    assert len(df) == 2
    assert list(df.columns) == ["category", "field_name", "column_name", "readable_name", "select_type"]
    assert df["readable_name"].iloc[0] == "Chỉ số P/E"
    assert df.attrs["source"] == "VIETCAP_IQ_DIRECT"


# ============================================================================
# 2. VNDIRECT FINFO DIRECT API TESTS
# ============================================================================

def test_fetch_market_rankings_gainer():
    """Kiểm tra bảng xếp hạng top gainer từ VNDIRECT FINFO."""
    mock_top_data = {
        "data": [
            {
                "code": "TNT",
                "index": "VNIndex",
                "lastPrice": 5.4,
                "lastUpdated": "2026-09-25 15:00:00",
                "priceChgCr1D": 0.35,
                "priceChgPctCr1D": 6.93,
                "accumulatedVal": 12500000000,
                "nmVolumeAvgCr20D": 450000,
                "nmVolNmVolAvg20DPctCr": 210.5,
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_top_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_market_rankings(category="gainer", index="VNINDEX", limit=5)

    assert not df.empty
    assert df["symbol"].iloc[0] == "TNT"
    assert df["price_change_percent_1d"].iloc[0] == 6.93
    assert df["volume_spike_20d_percent"].iloc[0] == 210.5
    assert df.attrs["source"] == "VNDIRECT_FINFO_DIRECT"
    assert df.attrs["category"] == "gainer"


def test_fetch_foreign_top_flows():
    """Kiểm tra dữ liệu top giao dịch khối ngoại từ VNDIRECT."""
    mock_foreign_data = {
        "data": [
            {
                "code": "HPG",
                "netVal": 85000000000,
                "tradingDate": "2026-09-25",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_foreign_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_foreign_top_flows(mode="buy", trading_date="2026-09-25")

    assert len(df) == 1
    assert df["symbol"].iloc[0] == "HPG"
    assert df["net_val"].iloc[0] == 85000000000
    assert df.attrs["source"] == "VNDIRECT_FINFO_DIRECT"


def test_fetch_index_valuation():
    """Kiểm tra chuỗi P/E lịch sử của chỉ số VN-Index từ VNDIRECT."""
    mock_valuation_data = {
        "data": [
            {"reportDate": "2026-09-25", "value": 12.32},
            {"reportDate": "2026-09-24", "value": 12.25},
            {"reportDate": "2026-09-23", "value": 12.43},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_valuation_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_index_valuation(index="VNINDEX", ratio_code="PRICE_TO_EARNINGS")

    assert len(df) == 3
    # Phải được sắp xếp theo thời gian tăng dần
    assert df["report_date"].iloc[0] == pd.Timestamp("2026-09-23")
    assert df["report_date"].iloc[-1] == pd.Timestamp("2026-09-25")
    assert df["value"].iloc[-1] == 12.32
    assert df.attrs["source"] == "VNDIRECT_FINFO_DIRECT"
    assert df.attrs["index"] == "VNINDEX"


# ============================================================================
# 3. ASEAN SECURITIES RESEARCH API TESTS (BREADTH & FEAR/GREED)
# ============================================================================

def test_fetch_market_breadth():
    """Kiểm tra độ rộng thị trường từ ASEAN Securities."""
    mock_breadth_data = {
        "data": [
            {
                "ExchangeCode": "HOSE",
                "TradeDate": "2026-09-25",
                "PE": 12.3,
                "PB": 2.01,
                "ABOVE_MA50_PCT": 48.5,
                "above_ma20_pct": 52.0,
                "position_line": 0.65,
                "close_index": 1285.4,
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_breadth_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_market_breadth(exchange="HOSE")

    assert len(df) == 1
    assert df["exchange"].iloc[0] == "HOSE"
    assert df["pe"].iloc[0] == 12.3
    assert df["above_ma50_pct"].iloc[0] == 48.5
    assert df["position_line"].iloc[0] == 0.65
    assert df.attrs["source"] == "ASEAN_SC_DIRECT"


def test_fetch_market_fear_greed():
    """Kiểm tra chỉ số Tham lam / Sợ hãi từ ASEAN Securities."""
    mock_fg_data = {
        "data": [
            {
                "FEAR_GREED": 42.5,
                "ADVANCES": 180,
                "DECLINES": 160,
                "NOCHANGE": 60,
                "MFI": 51.2,
                "RSI": 49.8,
                "INDEX_CHANGE": 1.25,
                "VOL_CHANGE": -5.4,
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_fg_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_market_fear_greed(exchange="HOSE")

    assert len(df) == 1
    assert df["fear_greed_score"].iloc[0] == 42.5
    assert df["advances"].iloc[0] == 180
    assert df["declines"].iloc[0] == 160
    assert df["mfi"].iloc[0] == 51.2
    assert df.attrs["source"] == "ASEAN_SC_DIRECT"


# ============================================================================
# 4. ASEAN SECURITIES MACROECONOMIC INDICATORS TESTS
# ============================================================================

def test_fetch_macro_indicator_gdp():
    """Kiểm tra chỉ số vĩ mô GDP và format ngày tháng."""
    mock_gdp_data = {
        "data": [
            {
                "reportDate": "2025-10-01",
                "GDP": 6.82,
                "AGR": 3.4,
                "IND": 7.1,
                "SER": 7.5,
                "TAX": 5.2,
                "VNI": 1270.0,
            },
            {
                "reportDate": "2026-01-01",
                "GDP": 7.15,
                "AGR": 3.6,
                "IND": 7.8,
                "SER": 7.9,
                "TAX": 5.5,
                "VNI": 1285.0,
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_gdp_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_macro_indicator(indicator="gdp", start_date="2025-01-01", end_date="2026-01-01")

    assert len(df) == 2
    assert "report_date" in df.columns
    assert df["gdp"].iloc[-1] == 7.15
    assert df.attrs["source"] == "ASEAN_SC_DIRECT"
    assert df.attrs["indicator"] == "gdp"


def test_fetch_macro_indicator_interbank():
    """Kiểm tra chỉ số lãi suất liên ngân hàng."""
    mock_ib_data = {
        "data": [
            {
                "reportDate": "2026-09-25",
                "interest": 4.15,
                "VNI": 1285.0,
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_ib_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        df = market_insights.fetch_macro_indicator(indicator="interbank_rate", period="ON")

    assert len(df) == 1
    assert df["interest"].iloc[0] == 4.15
    assert df.attrs["source"] == "ASEAN_SC_DIRECT"


def test_fetch_macro_indicator_invalid():
    """Kiểm tra chỉ số không hợp lệ ném ValueError."""
    with pytest.raises(ValueError, match="không được hỗ trợ"):
        market_insights.fetch_macro_indicator(indicator="non_existent_indicator")
