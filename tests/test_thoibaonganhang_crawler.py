"""Unit tests for Thoi Bao Ngan Hang Crawler (thoibaonganhang_crawler.py)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch, MagicMock

import duckdb
import pytest

from src.crawlers.thoibaonganhang_crawler import ThoiBaoNganHangCrawler


@pytest.fixture
def temp_duckdb(tmp_path):
    """Tạo database DuckDB test với schema core.macro_policy."""
    db_path = str(tmp_path / "test_tbnh.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("""
        CREATE TABLE core.macro_policy (
            source VARCHAR NOT NULL,
            issuing_body VARCHAR,
            doc_type VARCHAR,
            doc_number VARCHAR,
            published_at TIMESTAMP NOT NULL,
            available_at TIMESTAMP NOT NULL,
            headline VARCHAR NOT NULL,
            summary TEXT,
            body TEXT NOT NULL,
            source_url VARCHAR PRIMARY KEY,
            fetched_at TIMESTAMP NOT NULL
        );
    """)
    con.close()
    return db_path


def test_parse_article_links_and_next_url():
    """Kiểm tra trích xuất đúng link bài viết và URL trang tiếp theo."""
    html = """
    <div>
        <a href="https://thoibaonganhang.vn/ty-gia-trung-tam-186812.html">Tiêu đề 1</a>
        <a href="/ha-lai-suat-tin-dung-186729.html">Tiêu đề 2</a>
        <input class="__MB_NEXT_URL" value="https://thoibaonganhang.vn/apicenter@/article_lm&page=2" />
    </div>
    """
    links, next_url = ThoiBaoNganHangCrawler.parse_article_links(html)
    assert len(links) == 2
    assert "https://thoibaonganhang.vn/ty-gia-trung-tam-186812.html" in links
    assert "https://thoibaonganhang.vn/ha-lai-suat-tin-dung-186729.html" in links
    assert next_url == "https://thoibaonganhang.vn/apicenter@/article_lm&page=2"


def test_save_batch_success(temp_duckdb):
    """Kiểm tra lưu bài viết Thời báo Ngân hàng vào DuckDB thành công."""
    crawler = ThoiBaoNganHangCrawler(duckdb_path=temp_duckdb)

    articles = [{
        "source": "thoibaonganhang",
        "issuing_body": "Thời báo Ngân hàng - Ngân hàng Nhà nước Việt Nam",
        "doc_type": "Thị trường tiền tệ & Lãi suất",
        "doc_number": None,
        "published_at": dt.datetime(2026, 9, 4, 8, 30),
        "available_at": dt.datetime(2026, 9, 4, 8, 30),
        "headline": "NHNN điều hành linh hoạt tỷ giá trung tâm",
        "summary": "Tóm tắt bài viết NHNN",
        "body": "Chi tiết chính sách tiền tệ và lãi suất điều hành...",
        "source_url": "https://thoibaonganhang.vn/ty-gia-123.html",
        "fetched_at": dt.datetime(2026, 9, 4, 8, 35),
    }]

    count = crawler.save_batch(articles)
    assert count == 1

    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT source, headline FROM core.macro_policy WHERE source = 'thoibaonganhang'").fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0] == ("thoibaonganhang", "NHNN điều hành linh hoạt tỷ giá trung tâm")
