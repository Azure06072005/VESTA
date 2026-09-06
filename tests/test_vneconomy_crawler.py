"""Unit tests cho VnEconomy Macro & Sector Policy Crawler (vneconomy_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
from unittest.mock import MagicMock

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.vneconomy_crawler import (
    parse_vneconomy_datetime,
    extract_doc_number,
    parse_category_soup,
    parse_article_soup,
    VnEconomyCrawler,
)

SAMPLE_CATEGORY_HTML = """
<html>
<body>
<div class="category-page">
    <div class="story__title">
        <a href="/nhung-vung-dem-ho-tro-ty-gia-on-dinh-tu-nay-den-cuoi-nam.htm">
            Những “vùng đệm” hỗ trợ tỷ giá ổn định từ nay đến cuối năm
        </a>
    </div>
    <div class="story__title">
        <a href="/lai-suat-tiet-kiem-ngan-hang-nao-cao-nhat-thang-92026.htm">
            Lãi suất tiết kiệm ngân hàng nào cao nhất tháng 9/2026?
        </a>
    </div>
    <!-- Navigation link to be skipped -->
    <div class="story__title"><a href="/tai-chinh.htm">Tài chính</a></div>
    <div class="story__title"><a href="/tai-chinh.htm?page=2">2</a></div>
    <!-- Too short text -->
    <div class="story__title"><a href="/tin-ngan-moi-ve.htm">Ngắn</a></div>
</div>
</body>
</html>
"""

SAMPLE_ARTICLE_HTML = """
<html>
<head>
    <meta property="og:title" content="Những “vùng đệm” hỗ trợ tỷ giá ổn định từ nay đến cuối năm" />
    <meta property="og:description" content="Áp lực tỷ giá đang giảm nhờ sự kết hợp giữa đồng USD suy yếu và dòng vốn FDI giải ngân tích cực." />
</head>
<body>
    <div class="article-header">
        <h1 class="article-header__title">Những “vùng đệm” hỗ trợ tỷ giá ổn định từ nay đến cuối năm</h1>
        <div class="article-meta">
            <time class="article-meta__time">18:47, 20/08/2026</time>
        </div>
    </div>
    <div class="article-layout">
        <p>Yếu tố hỗ trợ gần nhất đến từ thị trường trái phiếu Mỹ sau khi Bộ Tài chính công bố tăng quy mô.</p>
        <p>Theo Thông tư 02/2023/TT-NHNN, các tổ chức tín dụng tiếp tục hỗ trợ khách hàng gặp khó khăn.</p>
        <p>Chọn cỡ chữ Nhỏ hơn Lớn hơn</p>
    </div>
</body>
</html>
"""


def test_parse_vneconomy_datetime():
    """Kiểm tra bóc tách chuỗi thời gian ICT sang UTC."""
    raw = "18:47, 20/08/2026"
    parsed = parse_vneconomy_datetime(raw)
    assert parsed.year == 2026
    assert parsed.month == 8
    assert parsed.day == 20
    assert parsed.hour == 11  # 18 - 7
    assert parsed.minute == 47

    # Chỉ có ngày
    parsed_date_only = parse_vneconomy_datetime("15/09/2026")
    assert parsed_date_only.year == 2026
    assert parsed_date_only.month == 9
    assert parsed_date_only.day == 14  # 00:00 - 7h = 17:00 ngày hôm trước


def test_extract_doc_number():
    """Kiểm tra trích xuất số hiệu văn bản pháp luật trích dẫn."""
    assert extract_doc_number("Chính sách mới", "Chi tiết tại Thông tư 02/2023/TT-NHNN", "") == "02/2023/TT-NHNN"
    assert extract_doc_number("Nghị định 52/2024/NĐ-CP về thanh toán không dùng tiền mặt", "", "") == "52/2024/NĐ-CP"
    assert extract_doc_number("Tin tức chung không văn bản", "Không có số", "Nội dung bình thường") is None


def test_parse_category_soup():
    """Kiểm tra trích xuất danh sách link bài viết từ trang chuyên mục."""
    articles = parse_category_soup(SAMPLE_CATEGORY_HTML, "tai-chinh.htm")
    assert len(articles) == 2
    assert articles[0]["url"] == "https://vneconomy.vn/nhung-vung-dem-ho-tro-ty-gia-on-dinh-tu-nay-den-cuoi-nam.htm"
    assert "tỷ giá" in articles[0]["title"]
    assert articles[1]["url"] == "https://vneconomy.vn/lai-suat-tiet-kiem-ngan-hang-nao-cao-nhat-thang-92026.htm"


def test_parse_article_soup():
    """Kiểm tra trích xuất chi tiết bài viết, bóc tách cơ quan ban hành theo văn bản."""
    url = "https://vneconomy.vn/nhung-vung-dem-ho-tro-ty-gia-on-dinh-tu-nay-den-cuoi-nam.htm"
    rec = parse_article_soup(SAMPLE_ARTICLE_HTML, url)
    assert rec is not None
    assert rec["source"] == "vneconomy"
    assert rec["headline"] == "Những “vùng đệm” hỗ trợ tỷ giá ổn định từ nay đến cuối năm"
    assert "Áp lực tỷ giá đang giảm" in rec["summary"]
    assert "Yếu tố hỗ trợ gần nhất" in rec["body"]
    assert "Chọn cỡ chữ" not in rec["body"]
    assert rec["doc_number"] == "02/2023/TT-NHNN"
    assert rec["issuing_body"] == "Ngân hàng Nhà nước Việt Nam"
    assert rec["source_url"] == url


def test_save_to_database(tmp_path):
    """Kiểm tra lưu dữ liệu vào DuckDB với kiểm soát khóa chính và upsert."""
    db_file = str(tmp_path / "test_vneconomy.duckdb")
    conn = duckdb.connect(db_file)
    conn.execute("CREATE SCHEMA staging")
    conn.execute("CREATE SCHEMA core")
    schema_sql = """
        CREATE TABLE staging.macro_policy (
            source VARCHAR,
            issuing_body VARCHAR,
            doc_type VARCHAR,
            doc_number VARCHAR,
            published_at TIMESTAMP,
            available_at TIMESTAMP,
            headline VARCHAR,
            summary VARCHAR,
            body VARCHAR,
            source_url VARCHAR,
            fetched_at TIMESTAMP
        );
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
        );
    """
    conn.execute(schema_sql)
    conn.close()

    crawler = VnEconomyCrawler(db_path=db_file)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    records = [
        {
            "source": "vneconomy",
            "issuing_body": "Ngân hàng Nhà nước Việt Nam",
            "doc_type": "Chính sách tiền tệ",
            "doc_number": "02/2023/TT-NHNN",
            "published_at": now,
            "available_at": now,
            "headline": "Tiêu đề 1",
            "summary": "Tóm tắt 1",
            "body": "Nội dung 1",
            "source_url": "https://vneconomy.vn/bai-1.htm",
            "fetched_at": now,
        },
        {
            "source": "vneconomy",
            "issuing_body": "Bộ Tài chính",
            "doc_type": "Chính sách thuế",
            "doc_number": None,
            "published_at": now,
            "available_at": now,
            "headline": "Tiêu đề 2",
            "summary": "Tóm tắt 2",
            "body": "Nội dung 2",
            "source_url": "https://vneconomy.vn/bai-2.htm",
            "fetched_at": now,
        },
    ]

    saved = crawler.save_to_database(records)
    assert saved == 2

    # Verify DuckDB contents
    check_conn = duckdb.connect(db_file, read_only=True)
    count_core = check_conn.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    count_staging = check_conn.execute("SELECT count(*) FROM staging.macro_policy").fetchone()[0]
    assert count_core == 2
    assert count_staging == 2
    check_conn.close()

    # Test idempotency on re-insertion
    saved_again = crawler.save_to_database(records)
    assert saved_again == 2
    check_conn2 = duckdb.connect(db_file, read_only=True)
    count_core_after = check_conn2.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    assert count_core_after == 2  # No duplicate primary key
    check_conn2.close()


def test_crawler_mocked_network():
    """Kiểm tra fetch_category_page và fetch_article với mock session."""
    mock_session = MagicMock()
    mock_resp_cat = MagicMock()
    mock_resp_cat.status_code = 200
    mock_resp_cat.text = SAMPLE_CATEGORY_HTML

    mock_resp_art = MagicMock()
    mock_resp_art.status_code = 200
    mock_resp_art.text = SAMPLE_ARTICLE_HTML

    mock_session.get.side_effect = [mock_resp_cat, mock_resp_art, mock_resp_art]

    crawler = VnEconomyCrawler(session=mock_session)
    pages = crawler.fetch_category_page("tai-chinh.htm", page=1)
    assert len(pages) == 2

    article = crawler.fetch_article("https://vneconomy.vn/sample.htm")
    assert article is not None
    assert article["headline"] == "Những “vùng đệm” hỗ trợ tỷ giá ổn định từ nay đến cuối năm"
