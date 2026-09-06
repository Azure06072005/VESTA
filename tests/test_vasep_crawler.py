"""Unit tests for VASEP seafood crawler."""

from __future__ import annotations

import datetime as dt
import duckdb
import pytest

from src.crawlers.vasep_crawler import (
    parse_vasep_sitemap,
    parse_vasep_article,
    VasepCrawler,
)

SAMPLE_VASEP_SITEMAP = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://vasep.com.vn/san-pham-xuat-khau/tom/xuat-nhap-khau/gsf-2026-tang-tieu-thu-tom-tai-eu-38101.html</loc>
        <lastmod>2026-09-04T12:56:00+07:00</lastmod>
    </url>
    <url>
        <loc>https://vasep.com.vn/chong-khai-thac-iuu/tin-tuc-iuu/cang-chattogram-siet-xu-ly-38102.html</loc>
        <lastmod>2026-09-04T15:15:00+07:00</lastmod>
    </url>
</urlset>
"""

SAMPLE_VASEP_ARTICLE = """<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="GSF 2026: Tăng tiêu thụ tôm tại EU từ thay đổi sản phẩm" />
    <meta property="article:published_time" content="2026-09-04T12:47:17+07:00" />
    <meta property="og:description" content="Các chuyên gia nhận định về xu hướng nhập khẩu tôm tại thị trường châu Âu." />
</head>
<body>
    <div class="content-detail">
        <p>Diễn đàn tôm toàn cầu (GSF) tại Utrecht (Hà Lan) đã thảo luận các giải pháp thúc đẩy tiêu thụ.</p>
        <p>Việt Nam tiếp tục là một trong những nhà cung ứng tôm chất lượng cao hàng đầu cho thị trường EU.</p>
    </div>
</body>
</html>
"""


def test_parse_vasep_sitemap() -> None:
    entries = parse_vasep_sitemap(SAMPLE_VASEP_SITEMAP)
    assert len(entries) == 2
    assert "38101.html" in entries[0]["url"]
    assert "38102.html" in entries[1]["url"]


def test_parse_vasep_article() -> None:
    url = "https://vasep.com.vn/san-pham-xuat-khau/tom/38101.html"
    art = parse_vasep_article(SAMPLE_VASEP_ARTICLE, url)
    assert art is not None
    assert art["source"] == "vasep"
    assert "GSF 2026: Tăng tiêu thụ tôm tại EU" in art["headline"]
    assert "nhà cung ứng tôm chất lượng cao" in art["body"]
    assert art["published_at"] is not None
    assert art["available_at"] == art["published_at"]  # Zero lookahead bias


def test_vasep_save_batch(tmp_path) -> None:
    db_file = str(tmp_path / "test_vasep.duckdb")
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

    crawler = VasepCrawler(duckdb_path=db_file)
    item = {
        "source": "vasep",
        "issuing_body": "VASEP",
        "doc_type": "industry_report",
        "doc_number": None,
        "published_at": dt.datetime(2026, 9, 4, 12, 0),
        "available_at": dt.datetime(2026, 9, 4, 12, 0),
        "headline": "Xuất khẩu cá tra tăng trưởng mạnh",
        "summary": "Tóm tắt xuất khẩu",
        "body": "Chi tiết xuất khẩu sang thị trường Hoa Kỳ và Trung Quốc",
        "source_url": "https://vasep.com.vn/sample-38101.html",
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    }

    n1 = crawler.save_batch([item])
    assert n1 == 1

    # Idempotent re-run
    n2 = crawler.save_batch([item])
    assert n2 == 1

    con = duckdb.connect(db_file, read_only=True)
    count = con.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'vasep'").fetchone()[0]
    con.close()
    assert count == 1
