"""Unit tests for CafeF Finance Enhancer (cafef_finance_enhancer.py)."""

from __future__ import annotations

import datetime as dt
import json

import duckdb
import pytest

from src.crawlers.cafef_finance_enhancer import CafeFFinanceEnhancer


@pytest.fixture
def temp_duckdb(tmp_path):
    """Tạo database DuckDB test với schema core.fundamentals và staging.fundamentals."""
    db_path = str(tmp_path / "test_fundamentals.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    con.execute("""
        CREATE TABLE core.fundamentals (
            symbol VARCHAR NOT NULL,
            report_type VARCHAR NOT NULL,
            period_end DATE NOT NULL,
            available_at TIMESTAMP NOT NULL,
            data_json JSON NOT NULL,
            fetched_at TIMESTAMP NOT NULL,
            source VARCHAR NOT NULL DEFAULT 'cafef',
            PRIMARY KEY (symbol, report_type, period_end, fetched_at)
        );
    """)
    con.execute("""
        CREATE TABLE staging.fundamentals (
            symbol VARCHAR NOT NULL,
            report_type VARCHAR NOT NULL,
            period_end DATE NOT NULL,
            available_at TIMESTAMP NOT NULL,
            data_json JSON NOT NULL,
            fetched_at TIMESTAMP NOT NULL,
            source VARCHAR NOT NULL DEFAULT 'cafef'
        );
    """)
    con.close()
    return db_path


def test_parse_quarter_period():
    """Kiểm tra phân tích cú pháp chuỗi kỳ quý sang ngày kết thúc chuẩn xác."""
    assert CafeFFinanceEnhancer._parse_quarter_period("Q1/2026") == dt.date(2026, 3, 31)
    assert CafeFFinanceEnhancer._parse_quarter_period("Q2/2026") == dt.date(2026, 6, 30)
    assert CafeFFinanceEnhancer._parse_quarter_period("Q3/2025") == dt.date(2025, 9, 30)
    assert CafeFFinanceEnhancer._parse_quarter_period("Q4/2025") == dt.date(2025, 12, 31)
    assert CafeFFinanceEnhancer._parse_quarter_period("2025") == dt.date(2025, 12, 31)
    assert CafeFFinanceEnhancer._parse_quarter_period("Invalid") is None


def test_parse_and_normalize():
    """Kiểm tra bóc tách cấu trúc templace và data theo quý của CafeF API."""
    raw_val = {
        "templace": [
            {"code": "1", "name": "TÀI SẢN NGẮN HẠN"},
            {"code": "2", "name": "Tiền và tương đương tiền"},
        ],
        "data": [
            {
                "symbol": "VCB",
                "year": 2026,
                "quater": 2,
                "time": "Q2-2026",
                "data": [
                    {"code": "1", "value": 1000000.0},
                    {"code": "2", "value": 200000.0},
                ]
            },
            {
                "symbol": "VCB",
                "year": 2026,
                "quater": 1,
                "time": "Q1-2026",
                "data": [
                    {"code": "1", "value": 950000.0},
                    {"code": "2", "value": 180000.0},
                ]
            }
        ]
    }
    enhancer = CafeFFinanceEnhancer(duckdb_path=":memory:")
    records = enhancer.parse_and_normalize("VCB", "balance_sheet", raw_val)

    assert len(records) == 2
    rec_q2 = next(r for r in records if r["period_end"] == dt.date(2026, 6, 30))
    metrics_q2 = json.loads(rec_q2["data_json"])
    assert metrics_q2["TÀI SẢN NGẮN HẠN"] == 1000000.0
    assert metrics_q2["Tiền và tương đương tiền"] == 200000.0

    # Kiểm tra tính tuân thủ Zero Look-Ahead Bias: available_at = period_end + 30 days
    assert rec_q2["available_at"].date() == dt.date(2026, 7, 30)


def test_save_batch(temp_duckdb):
    """Kiểm tra lưu trữ vào DuckDB và cơ chế ON CONFLICT."""
    enhancer = CafeFFinanceEnhancer(duckdb_path=temp_duckdb)
    now = dt.datetime.now(dt.timezone.utc)
    records = [
        {
            "symbol": "FPT",
            "report_type": "income_statement",
            "period_end": dt.date(2026, 6, 30),
            "available_at": dt.datetime(2026, 7, 30, 0, 0, tzinfo=dt.timezone.utc),
            "data_json": json.dumps({"Doanh thu thuần": 5000000.0}),
            "fetched_at": now,
            "source": "cafef",
        }
    ]
    saved = enhancer.save_batch(records)
    assert saved == 1

    con = duckdb.connect(temp_duckdb)
    row = con.execute("SELECT symbol, report_type, data_json FROM core.fundamentals").fetchone()
    con.close()

    assert row[0] == "FPT"
    assert row[1] == "income_statement"
    assert "5000000.0" in row[2]


def test_normalize_financial_dict_balance_sheet():
    """Kiểm tra bóc tách và chuẩn hóa tự động các chỉ tiêu bảng CĐKT sang tiếng Anh."""
    from src.etl.vas_dictionary import normalize_financial_dict

    raw_metrics = {
        "100": 5000000.0,
        "TỔNG CỘNG TÀI SẢN": 5000000.0,
        "110": 2000000.0,
        "TÀI SẢN NGẮN HẠN": 2000000.0,
        "Tiền và tương đương tiền": 500000.0,
        "Hàng tồn kho": 800000.0,
        "300": 3000000.0,
        "Nợ phải trả": 3000000.0,
        "Nợ ngắn hạn": 1500000.0,
        "400": 2000000.0,
        "Vốn chủ sở hữu": 2000000.0,
    }
    normalized = normalize_financial_dict(raw_metrics, "balance_sheet")

    # Giữ nguyên bản gốc tiếng Việt và code
    assert normalized["TỔNG CỘNG TÀI SẢN"] == 5000000.0
    assert normalized["100"] == 5000000.0

    # Chuẩn hóa bổ sung key tiếng Anh tương ứng vnstock_data
    assert normalized["total_assets"] == 5000000.0
    assert normalized["current_assets"] == 2000000.0
    assert normalized["cash_and_equivalents"] == 500000.0
    assert normalized["inventories"] == 800000.0
    assert normalized["liabilities"] == 3000000.0
    assert normalized["current_liabilities"] == 1500000.0
    assert normalized["owners_equity"] == 2000000.0


def test_normalize_financial_dict_income_statement():
    """Kiểm tra chuẩn hóa KQKD sang tiếng Anh."""
    from src.etl.vas_dictionary import normalize_financial_dict

    raw_metrics = {
        "Doanh thu thuần": 1200000.0,
        "Giá vốn hàng bán": 800000.0,
        "Lợi nhuận gộp": 400000.0,
        "Chi phí tài chính": 50000.0,
        "Chi phí bán hàng": 70000.0,
        "Lợi nhuận sau thuế": 250000.0,
        "Lãi cơ bản trên cổ phiếu (EPS)": 3500.0,
    }
    normalized = normalize_financial_dict(raw_metrics, "income_statement")

    assert normalized["net_revenue"] == 1200000.0
    assert normalized["cogs"] == 800000.0
    assert normalized["gross_profit"] == 400000.0
    assert normalized["financial_expenses"] == 50000.0
    assert normalized["selling_expenses"] == 70000.0
    assert normalized["net_profit_after_tax"] == 250000.0
    assert normalized["eps"] == 3500.0


def test_downstream_ml_feature_compatibility():
    """Kiểm tra dữ liệu chuẩn hóa của CafeFFinanceEnhancer tương thích 1:1 với ml_features.py."""
    from src.pipeline.ml_features import extract_fundamental_features

    raw_val = {
        "templace": [
            {"code": "P/E", "name": "P/E"},
            {"code": "P/B", "name": "P/B"},
            {"code": "ROE", "name": "ROE (%)"},
        ],
        "data": [
            {
                "symbol": "MBB",
                "year": 2026,
                "quater": 2,
                "time": "Q2-2026",
                "data": [
                    {"code": "P/E", "value": 6.5},
                    {"code": "P/B", "value": 1.1},
                    {"code": "ROE", "value": 22.4},
                ]
            }
        ]
    }
    enhancer = CafeFFinanceEnhancer(duckdb_path=":memory:")
    records = enhancer.parse_and_normalize("MBB", "ratio", raw_val)

    assert len(records) == 1
    # Bóc tách bằng hàm downstream của pipeline machine learning
    features = extract_fundamental_features(records[0]["data_json"])
    assert features["pe_ratio"] == 6.5
    assert features["pb_ratio"] == 1.1
    assert features["roe"] == 22.4

