"""Unit tests cho Vietstock Market & Financial Policy Crawler (vietstock_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
from unittest.mock import MagicMock

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.vietstock_crawler import (
    parse_iso_or_vn_datetime,
    extract_doc_number,
    parse_category_soup,
    parse_article_soup,
    VietstockCrawler,
)

SAMPLE_CATEGORY_HTML = """
<div class="news-list">
    <div class="single_post">
        <h4>
            <a href="/2026/09/theo-dau-dong-tien-ca-map-0409-khoi-ngoai-mua-rong-119-ty-dong-tu-doanh-ban-rong-168-ty-dong-830-1488880.htm">
                Theo dấu dòng tiền cá mập 04/09: Khối ngoại mua ròng 119 tỷ đồng, tự doanh bán ròng 168 tỷ đồng
            </a>
        </h4>
    </div>
    <div class="single_post">
        <h4>
            <a href="/2026/09/21-co-phieu-viet-bi-loai-khoi-ro-ftse-vietnam-index-3358-1488907.htm">
                21 cổ phiếu Việt bị loại khỏi rổ FTSE Vietnam Index
            </a>
        </h4>
    </div>
    <!-- Irrelevant non-article link -->
    <a href="/tin-tuc.htm">Xem thêm</a>
</div>
"""

SAMPLE_ARTICLE_HTML = """
<html>
<head>
    <script type="application/ld+json">
    {
        "@context": "http://schema.org",
        "@type": "NewsArticle",
        "headline": "Theo dấu dòng tiền cá mập 04/09: Khối ngoại mua ròng 119 tỷ đồng | Vietstock",
        "datePublished": "2026-09-04T19:32:00+07:00",
        "description": "Phiên giao dịch ngày 04/09 chứng kiến sự trái chiều của hai dòng tiền lớn."
    }
    </script>
</head>
<body>
    <h1 class="article-title">Theo dấu dòng tiền cá mập 04/09: Khối ngoại mua ròng 119 tỷ đồng</h1>
    <div id="vst_detail">
        <p>Phiên giao dịch ngày 04/09 chứng kiến sự trái chiều của hai dòng tiền lớn.</p>
        <p>Theo Thông tư 68/2024/TT-BTC về giao dịch không yêu cầu ký quỹ 100% đối với khối ngoại.</p>
        <p>Khối ngoại ghi nhận phiên mua ròng với giá trị đạt 119 tỷ đồng.</p>
    </div>
</body>
</html>
"""


def test_parse_iso_or_vn_datetime():
    """Kiểm tra parse thời gian ISO 8601 từ JSON-LD và định dạng tiếng Việt sang UTC."""
    iso_raw = "2026-09-04T19:32:00+07:00"
    parsed = parse_iso_or_vn_datetime(iso_raw)
    assert parsed.year == 2026
    assert parsed.month == 9
    assert parsed.day == 4
    assert parsed.hour == 12  # 19 - 7
    assert parsed.minute == 32

    # Parse chuỗi ngày tháng tiếng Việt
    vn_raw = "04/09/2026 15:30"
    parsed_vn = parse_iso_or_vn_datetime(vn_raw)
    assert parsed_vn.year == 2026
    assert parsed_vn.month == 9
    assert parsed_vn.day == 4
    assert parsed_vn.hour == 8  # 15 - 7


def test_extract_doc_number():
    """Kiểm tra bóc tách số hiệu văn bản pháp lý trích dẫn."""
    assert extract_doc_number("Chính sách mới", "Căn cứ Thông tư 68/2024/TT-BTC về nâng hạng", "") == "68/2024/TT-BTC"
    assert extract_doc_number("Nghị định 155/2020/NĐ-CP chi tiết Luật Chứng khoán", "", "") == "155/2020/NĐ-CP"
    assert extract_doc_number("Thị trường chung", "Không có số hiệu", "") is None


def test_parse_category_soup():
    """Kiểm tra trích xuất danh sách link bài viết từ kết quả ChannelContentPage."""
    articles = parse_category_soup(SAMPLE_CATEGORY_HTML, "chung-khoan")
    assert len(articles) == 2
    assert "1488880.htm" in articles[0]["url"]
    assert "cá mập" in articles[0]["title"]
    assert "1488907.htm" in articles[1]["url"]
    assert "FTSE" in articles[1]["title"]


def test_parse_article_soup():
    """Kiểm tra bóc tách chi tiết bài viết từ JSON-LD và div#vst_detail."""
    url = "https://vietstock.vn/2026/09/test-article-1488880.htm"
    rec = parse_article_soup(SAMPLE_ARTICLE_HTML, url, default_doc_type="Thị trường chứng khoán")
    assert rec is not None
    assert rec["source"] == "vietstock"
    assert rec["headline"] == "Theo dấu dòng tiền cá mập 04/09: Khối ngoại mua ròng 119 tỷ đồng"
    assert "sự trái chiều" in rec["summary"]
    assert "119 tỷ đồng" in rec["body"]
    assert rec["doc_number"] == "68/2024/TT-BTC"
    assert rec["issuing_body"] == "Bộ Tài chính"
    assert rec["source_url"] == url


def test_save_to_database(tmp_path):
    """Kiểm tra lưu dữ liệu vào DuckDB với kiểm soát khóa chính và upsert."""
    db_file = str(tmp_path / "test_vietstock.duckdb")
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

    crawler = VietstockCrawler(db_path=db_file)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    records = [
        {
            "source": "vietstock",
            "issuing_body": "Cổng thông tin Tài chính Vietstock",
            "doc_type": "Thị trường chứng khoán",
            "doc_number": None,
            "published_at": now,
            "available_at": now,
            "headline": "Bài viết 1",
            "summary": "Tóm tắt 1",
            "body": "Nội dung 1",
            "source_url": "https://vietstock.vn/bai-1.htm",
            "fetched_at": now,
        },
        {
            "source": "vietstock",
            "issuing_body": "Bộ Tài chính",
            "doc_type": "Thông tư",
            "doc_number": "68/2024/TT-BTC",
            "published_at": now,
            "available_at": now,
            "headline": "Bài viết 2",
            "summary": "Tóm tắt 2",
            "body": "Nội dung 2",
            "source_url": "https://vietstock.vn/bai-2.htm",
            "fetched_at": now,
        },
    ]

    saved = crawler.save_to_database(records)
    assert saved == 2

    # Verify contents
    check_conn = duckdb.connect(db_file, read_only=True)
    assert check_conn.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'vietstock'").fetchone()[0] == 2
    check_conn.close()

    # Test idempotency on re-insertion
    saved_again = crawler.save_to_database(records)
    assert saved_again == 2
    check_conn2 = duckdb.connect(db_file, read_only=True)
    assert check_conn2.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'vietstock'").fetchone()[0] == 2
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

    mock_session.post.return_value = mock_resp_cat
    mock_session.get.return_value = mock_resp_art

    crawler = VietstockCrawler(session=mock_session)
    pages = crawler.fetch_category_page("chung-khoan", page=1)
    assert len(pages) == 2

    article = crawler.fetch_article("https://vietstock.vn/test.htm")
    assert article is not None
    assert article["headline"] == "Theo dấu dòng tiền cá mập 04/09: Khối ngoại mua ròng 119 tỷ đồng"
    assert article["doc_number"] == "68/2024/TT-BTC"
