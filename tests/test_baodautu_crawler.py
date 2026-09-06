"""Unit tests for Bao Dau Tu Crawler (baodautu_crawler.py)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch, MagicMock

import duckdb
import pytest

from src.crawlers.baodautu_crawler import BaoDauTuCrawler


@pytest.fixture
def temp_duckdb(tmp_path):
    """Tạo database DuckDB test với schema core.macro_policy."""
    db_path = str(tmp_path / "test_bdt.duckdb")
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


def test_parse_article_links():
    """Kiểm tra trích xuất đúng link bài viết từ HTML Báo Đầu tư."""
    html = """
    <div>
        <a href="/doanh-nghiep-tang-truong-manh-d481381.html">Tiêu đề 1</a>
        <a href="https://baodautu.vn/ngan-hang-ha-lai-suat-d481382.html">Tiêu đề 2</a>
        <a href="/video/tin-tuc-123.html">Video bỏ qua</a>
        <a href="/rss.html">RSS bỏ qua</a>
    </div>
    """
    links = BaoDauTuCrawler.parse_article_links(html)
    assert len(links) == 2
    assert "https://baodautu.vn/doanh-nghiep-tang-truong-manh-d481381.html" in links
    assert "https://baodautu.vn/ngan-hang-ha-lai-suat-d481382.html" in links


def test_save_batch_success(temp_duckdb):
    """Kiểm tra lưu bài viết Báo Đầu tư vào core.macro_policy thành công."""
    crawler = BaoDauTuCrawler(duckdb_path=temp_duckdb)

    articles = [{
        "source": "baodautu",
        "issuing_body": "Báo Đầu tư - Bộ Kế hoạch và Đầu tư",
        "doc_type": "Thị trường chứng khoán",
        "doc_number": None,
        "published_at": dt.datetime(2026, 9, 4, 10, 0),
        "available_at": dt.datetime(2026, 9, 4, 10, 0),
        "headline": "Thị trường chứng khoán đón dòng vốn mới",
        "summary": "Tóm tắt bài viết",
        "body": "Nội dung bài viết chi tiết...",
        "source_url": "https://baodautu.vn/test-d123.html",
        "fetched_at": dt.datetime(2026, 9, 4, 10, 5),
    }]

    count = crawler.save_batch(articles)
    assert count == 1

    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT source, headline FROM core.macro_policy WHERE source = 'baodautu'").fetchall()
    con.close()
    assert len(rows) == 1
    assert rows[0] == ("baodautu", "Thị trường chứng khoán đón dòng vốn mới")
