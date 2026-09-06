"""Unit tests for Tin Nhanh Chung Khoan crawler."""

from __future__ import annotations

import datetime as dt
import duckdb
import pytest

from src.crawlers.tinnhanhchungkhoan_crawler import (
    parse_sitemap_urls,
    parse_article_html,
    TinNhanhChungKhoanCrawler,
)

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://www.tinnhanhchungkhoan.vn</loc>
        <lastmod>2026-09-05T17:00:00+07:00</lastmod>
    </url>
    <url>
        <loc>https://www.tinnhanhchungkhoan.vn/sabeco-sab-tien-mat-lon-post396523.html</loc>
        <lastmod>2026-09-04T10:30:00+07:00</lastmod>
    </url>
    <url>
        <loc>https://www.tinnhanhchungkhoan.vn/bmi-ngay-gdkhq-tra-co-tuc-post396866.html</loc>
        <lastmod>2026-09-01T20:42:00+07:00</lastmod>
    </url>
</urlset>
"""

SAMPLE_ARTICLE_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="SAB: Tiền mặt dồi dào, định giá hấp dẫn trong dài hạn" />
    <meta property="article:published_time" content="2026-09-04T10:30:00+07:00" />
    <meta property="og:description" content="Sabeco duy trì lượng tiền mặt ròng khổng lồ và vị thế dẫn đầu ngành bia." />
</head>
<body>
    <div class="article__body">
        <p>Tổng công ty Bia - Rượu - Nước giải khát Sài Gòn (Sabeco, SAB) tiếp tục khẳng định vị thế tài chính vững chắc.</p>
        <p>Doanh nghiệp sở hữu hơn 20.000 tỷ đồng tiền và tương đương tiền gửi ngân hàng.</p>
    </div>
</body>
</html>
"""


def test_parse_sitemap_urls() -> None:
    entries = parse_sitemap_urls(SAMPLE_SITEMAP)
    assert len(entries) == 2
    assert entries[0]["url"] == "https://www.tinnhanhchungkhoan.vn/sabeco-sab-tien-mat-lon-post396523.html"
    assert "2026-09-04" in entries[0]["lastmod"]
    assert entries[1]["url"] == "https://www.tinnhanhchungkhoan.vn/bmi-ngay-gdkhq-tra-co-tuc-post396866.html"


def test_parse_article_html() -> None:
    url = "https://www.tinnhanhchungkhoan.vn/sabeco-sab-tien-mat-lon-post396523.html"
    res = parse_article_html(SAMPLE_ARTICLE_HTML, url)
    assert res is not None
    assert res["source"] == "tinnhanhchungkhoan"
    assert "SAB: Tiền mặt dồi dào" in res["headline"]
    assert "20.000 tỷ đồng tiền" in res["body"]
    assert res["published_at"] is not None
    assert res["available_at"] == res["published_at"]  # B4 Zero Look-Ahead Bias


def test_save_batch_idempotent(tmp_path) -> None:
    db_file = str(tmp_path / "test_macro.duckdb")
    con = duckdb.connect(db_file)
    con.execute("CREATE SCHEMA core")
    con.execute("""
        CREATE TABLE core.macro_policy (
            source VARCHAR,
            issuing_body VARCHAR,
            doc_type VARCHAR,
            doc_number VARCHAR,
            published_at TIMESTAMP,
            available_at TIMESTAMP,
            headline VARCHAR,
            summary VARCHAR,
            body VARCHAR,
            source_url VARCHAR PRIMARY KEY,
            fetched_at TIMESTAMP
        )
    """)
    con.close()

    crawler = TinNhanhChungKhoanCrawler(duckdb_path=db_file)
    sample_item = {
        "source": "tinnhanhchungkhoan",
        "issuing_body": "Tin Nhanh Chứng Khoán",
        "doc_type": "news",
        "doc_number": None,
        "published_at": dt.datetime(2026, 9, 4, 10, 30),
        "available_at": dt.datetime(2026, 9, 4, 10, 30),
        "headline": "SAB: Định giá thấp",
        "summary": "Tóm tắt",
        "body": "Nội dung phân tích chi tiết mã SAB",
        "source_url": "https://www.tinnhanhchungkhoan.vn/sab-post1.html",
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    }

    # Nạp lần 1
    cnt1 = crawler.save_batch([sample_item])
    assert cnt1 == 1

    # Nạp lần 2 (Idempotency - không nhân bản bản ghi)
    sample_item["headline"] = "SAB: Định giá cực kỳ hấp dẫn"
    cnt2 = crawler.save_batch([sample_item])
    assert cnt2 == 1

    con = duckdb.connect(db_file, read_only=True)
    rows = con.execute("SELECT count(*), max(headline) FROM core.macro_policy WHERE source = 'tinnhanhchungkhoan'").fetchall()
    con.close()
    assert rows[0][0] == 1
    assert rows[0][1] == "SAB: Định giá cực kỳ hấp dẫn"
