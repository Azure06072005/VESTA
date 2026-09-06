"""Unit tests for Vietstock Finance Enhancer (vietstock_finance_enhancer.py)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from src.crawlers.vietstock_finance_enhancer import VietstockFinanceEnhancer


@pytest.fixture
def temp_duckdb(tmp_path):
    """Tạo database DuckDB test với schema core.stock_research_reports."""
    db_path = str(tmp_path / "test_finance.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("""
        CREATE TABLE core.stock_research_reports (
            report_id VARCHAR,
            symbol VARCHAR,
            broker VARCHAR,
            title VARCHAR NOT NULL,
            recommendation VARCHAR,
            target_price DOUBLE,
            upside_pct DOUBLE,
            report_date DATE,
            report_url VARCHAR PRIMARY KEY,
            pdf_url VARCHAR,
            summary TEXT,
            fetched_at TIMESTAMP NOT NULL
        );
    """)
    con.close()
    return db_path


def test_parse_report_items():
    """Kiểm tra trích xuất đúng symbol, recommendation và target_price từ HTML fragment."""
    html_fragment = """
    <div>
        <a href="/bao-cao-phan-tich/21997/anv-khuyen-nghi-mua-voi-gia-muc-tieu-25000-dongco-phieu.htm">
            ANV: Khuyến nghị MUA với giá mục tiêu 25,000 đồng/cổ phiếu
        </a>
        <a href="/bao-cao-phan-tich/21996/vib-khuyen-nghi-theo-doi-voi-gia-muc-tieu-14200-dongco-phieu.htm">
            VIB: Khuyến nghị THEO DÕI với giá mục tiêu 14,200 đồng/cổ phiếu
        </a>
        <a href="/bao-cao-phan-tich/22002/vib-bao-cao-cap-nhat-kqkd-q22026.htm">
            VIB: Báo cáo cập nhật KQKD Q2/2026
        </a>
    </div>
    """
    items = VietstockFinanceEnhancer.parse_report_items(html_fragment)
    assert len(items) == 3

    # Mục 1: ANV MUA 25,000
    assert items[0]["symbol"] == "ANV"
    assert items[0]["recommendation"] == "MUA"
    assert items[0]["target_price"] == 25000.0
    assert items[0]["report_id"] == "21997"
    assert "21997" in items[0]["report_url"]

    # Mục 2: VIB THEO DÕI 14,200
    assert items[1]["symbol"] == "VIB"
    assert items[1]["recommendation"] == "THEO DÕI"
    assert items[1]["target_price"] == 14200.0

    # Mục 3: VIB không có khuyến nghị trực tiếp trong tiêu đề
    assert items[2]["symbol"] == "VIB"
    assert items[2]["recommendation"] is None
    assert items[2]["target_price"] is None


def test_save_reports_batch(temp_duckdb):
    """Kiểm tra lưu danh sách báo cáo vào DuckDB thành công và khử trùng lặp."""
    enhancer = VietstockFinanceEnhancer(duckdb_path=temp_duckdb)

    reports = [
        {
            "report_id": "21997",
            "symbol": "ANV",
            "broker": "Mirae Asset",
            "title": "ANV: Khuyến nghị MUA với giá mục tiêu 25,000 đồng",
            "recommendation": "MUA",
            "target_price": 25000.0,
            "upside_pct": 18.5,
            "report_date": dt.date(2026, 9, 3),
            "report_url": "https://finance.vietstock.vn/bao-cao-phan-tich/21997/anv.htm",
            "pdf_url": "http://static1.vietstock.vn/edocs/21997/ANV.pdf",
            "summary": "Tóm tắt báo cáo ANV",
        },
        {
            "report_id": "22002",
            "symbol": "VIB",
            "broker": "VPBankS",
            "title": "VIB: Báo cáo cập nhật KQKD Q2/2026",
            "recommendation": "KHẢ QUAN",
            "target_price": 16900.0,
            "upside_pct": 14.7,
            "report_date": dt.date(2026, 9, 4),
            "report_url": "https://finance.vietstock.vn/bao-cao-phan-tich/22002/vib.htm",
            "pdf_url": "http://static1.vietstock.vn/edocs/22002/VIB.pdf",
            "summary": "Tóm tắt báo cáo VIB",
        },
    ]

    saved_count = enhancer.save_reports_batch(reports)
    assert saved_count == 2

    # Xác thực trong DuckDB
    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT symbol, broker, target_price, recommendation FROM core.stock_research_reports ORDER BY symbol").fetchall()
    con.close()
    assert len(rows) == 2
    assert rows[0] == ("ANV", "Mirae Asset", 25000.0, "MUA")
    assert rows[1] == ("VIB", "VPBankS", 16900.0, "KHẢ QUAN")


def test_idempotent_upsert(temp_duckdb):
    """Kiểm tra tính bất biến (idempotency) khi ghi đè báo cáo cùng URL."""
    enhancer = VietstockFinanceEnhancer(duckdb_path=temp_duckdb)

    report_v1 = [{
        "report_id": "1001",
        "symbol": "HPG",
        "broker": "SSI",
        "title": "HPG Khuyến nghị Nắm giữ",
        "recommendation": "NẮM GIỮ",
        "target_price": 28000.0,
        "upside_pct": 5.0,
        "report_date": dt.date(2026, 8, 1),
        "report_url": "https://finance.vietstock.vn/bao-cao-phan-tich/1001/hpg.htm",
        "pdf_url": None,
        "summary": "Phiên bản cũ",
    }]
    enhancer.save_reports_batch(report_v1)

    # Cập nhật với dữ liệu mới hơn (ví dụ tìm thấy PDF và giá mục tiêu mới)
    report_v2 = [{
        "report_id": "1001",
        "symbol": "HPG",
        "broker": "SSI",
        "title": "HPG Khuyến nghị MUA",
        "recommendation": "MUA",
        "target_price": 32000.0,
        "upside_pct": 15.0,
        "report_date": dt.date(2026, 8, 1),
        "report_url": "https://finance.vietstock.vn/bao-cao-phan-tich/1001/hpg.htm",
        "pdf_url": "https://static1.vietstock.vn/edocs/1001/HPG.pdf",
        "summary": "Phiên bản mới cập nhật",
    }]
    enhancer.save_reports_batch(report_v2)

    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT target_price, recommendation, pdf_url FROM core.stock_research_reports WHERE symbol='HPG'").fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0] == (32000.0, "MUA", "https://static1.vietstock.vn/edocs/1001/HPG.pdf")
