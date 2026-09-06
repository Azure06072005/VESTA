"""Unit tests cho bộ cào chính sách năng lượng & công nghiệp Bộ Công Thương (moit_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
from unittest.mock import MagicMock

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.moit_crawler import (
    parse_moit_datetime,
    extract_doc_number,
    parse_category_soup,
    parse_article_soup,
    MoitCrawler,
)

SAMPLE_CATEGORY_HTML = """
<html>
<body>
<div class="news-list">
    <a href="/tin-tuc/thong-bao/mot-so-thong-tin-ve-viec-dieu-hanh-gia-xang-dau-ngay-3-9.html">
        Một số thông tin về việc điều hành giá xăng dầu ngày 3-9
    </a>
    <a href="/tin-tuc/phat-trien-nang-luong/bo-cong-thuong-phe-duyet-khung-gia-phat-dien-nhiet-dien-khi-nam-2026.html">
        Bộ Công Thương phê duyệt khung giá phát điện nhiệt điện khí năm 2026
    </a>
    <!-- Link too short to be an article -->
    <a href="/tin-tuc/thong-bao/ngan.html">Tin vắn</a>
    <!-- External or unrelated link -->
    <a href="/trang-chu.html">Trang chủ</a>
</div>
</body>
</html>
"""

SAMPLE_ARTICLE_HTML = """
<html>
<head>
    <meta property="og:title" content="Bộ Công Thương phê duyệt khung giá phát điện nhiệt điện khí năm 2026" />
    <meta property="og:description" content="Bộ Công Thương ban hành Quyết định 1882/QĐ-BCT phê duyệt khung giá phát điện nhiệt điện khí năm 2026." />
</head>
<body>
    <h1>Bộ Công Thương phê duyệt khung giá phát điện nhiệt điện khí năm 2026</h1>
    <div class="post-date">Thứ 2, 27/07/2026 | 14:19</div>
    <div class="content-detail">
        <p>Căn cứ Luật Điện lực và tình hình thị trường năng lượng sơ cấp, Bộ Công Thương ban hành Quyết định 1882/QĐ-BCT.</p>
        <p>Mức giá tối đa cho nhà máy nhiệt điện khí LNG là 3.410,64 đồng/kWh (chưa bao gồm thuế giá trị gia tăng).</p>
        <p>Tập đoàn Điện lực Việt Nam và các đơn vị phát điện chịu trách nhiệm thỏa thuận giá mua bán điện theo quy định.</p>
    </div>
</body>
</html>
"""


def test_parse_moit_datetime():
    """Kiểm tra bóc tách chuỗi thời gian Bộ Công Thương ICT sang UTC."""
    raw = "Thứ 2, 27/07/2026 | 14:19"
    parsed = parse_moit_datetime(raw)
    assert parsed.year == 2026
    assert parsed.month == 7
    assert parsed.day == 27
    assert parsed.hour == 7  # 14 - 7 ICT
    assert parsed.minute == 19

    # Định dạng chỉ có ngày
    parsed_date_only = parse_moit_datetime("03/09/2026")
    assert parsed_date_only.year == 2026
    assert parsed_date_only.month == 9
    assert parsed_date_only.day == 2  # 00:00 - 7h = 17:00 ngày hôm trước


def test_extract_doc_number():
    """Kiểm tra trích xuất số hiệu văn bản điều hành của BCT."""
    assert extract_doc_number("Ban hành Quyết định 1882/QĐ-BCT", "", "") == "1882/QĐ-BCT"
    assert extract_doc_number("Thông tư số 09/2026/TT-BCT về quy chuẩn kỹ thuật", "", "") == "09/2026/TT-BCT"
    assert extract_doc_number("Theo Nghị định 83/2014/NĐ-CP về kinh doanh xăng dầu", "", "") == "83/2014/NĐ-CP"
    assert extract_doc_number("Bài viết chung chung không có số hiệu văn bản", "", "") is None


def test_parse_category_soup():
    """Kiểm tra bóc tách danh sách bài viết từ trang chuyên mục MOIT."""
    articles = parse_category_soup(SAMPLE_CATEGORY_HTML, "thong-bao")
    assert len(articles) == 2
    assert "xăng dầu" in articles[0]["title"]
    assert articles[0]["url"] == "https://moit.gov.vn/tin-tuc/thong-bao/mot-so-thong-tin-ve-viec-dieu-hanh-gia-xang-dau-ngay-3-9.html"
    assert "nhiệt điện khí" in articles[1]["title"]


def test_parse_article_soup():
    """Kiểm tra bóc tách chi tiết bài viết chính sách MOIT."""
    url = "https://moit.gov.vn/tin-tuc/phat-trien-nang-luong/bo-cong-thuong-phe-duyet-khung-gia-phat-dien-nhiet-dien-khi-nam-2026.html"
    rec = parse_article_soup(SAMPLE_ARTICLE_HTML, url)
    assert rec is not None
    assert rec["source"] == "moit"
    assert rec["issuing_body"] == "Bộ Công Thương"
    assert rec["doc_type"] == "Quyết định phê duyệt"
    assert rec["doc_number"] == "1882/QĐ-BCT"
    assert rec["headline"] == "Bộ Công Thương phê duyệt khung giá phát điện nhiệt điện khí năm 2026"
    assert "3.410,64" in rec["body"]
    assert rec["source_url"] == url


def test_save_to_database(tmp_path):
    """Kiểm tra lưu dữ liệu vào DuckDB với tính năng upsert và khóa chính."""
    db_file = str(tmp_path / "test_moit.duckdb")
    conn = duckdb.connect(db_file)
    conn.execute("CREATE SCHEMA staging; CREATE SCHEMA core;")
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

    crawler = MoitCrawler(db_path=db_file)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    records = [
        {
            "source": "moit",
            "issuing_body": "Bộ Công Thương",
            "doc_type": "Quyết định phê duyệt",
            "doc_number": "1882/QĐ-BCT",
            "published_at": now,
            "available_at": now,
            "headline": "Tiêu đề test 1",
            "summary": "Tóm tắt test 1",
            "body": "Nội dung test 1",
            "source_url": "https://moit.gov.vn/test-1.html",
            "fetched_at": now,
        }
    ]

    saved = crawler.save_to_database(records)
    assert saved == 1

    # Kiểm tra tính toàn vẹn
    check_conn = duckdb.connect(db_file, read_only=True)
    count = check_conn.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'moit'").fetchone()[0]
    assert count == 1
    check_conn.close()

    # Kiểm tra idempotency (chèn lại cùng source_url)
    saved_again = crawler.save_to_database(records)
    assert saved_again == 1
    check_conn2 = duckdb.connect(db_file, read_only=True)
    count2 = check_conn2.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'moit'").fetchone()[0]
    assert count2 == 1  # Không bị nhân đôi bản ghi
    check_conn2.close()


def test_crawler_mocked_network():
    """Kiểm tra fetch_category_articles và fetch_article với mock session."""
    mock_session = MagicMock()
    mock_resp_cat = MagicMock()
    mock_resp_cat.status_code = 200
    mock_resp_cat.text = SAMPLE_CATEGORY_HTML

    mock_resp_art = MagicMock()
    mock_resp_art.status_code = 200
    mock_resp_art.text = SAMPLE_ARTICLE_HTML

    mock_session.get.side_effect = [mock_resp_cat, mock_resp_art]

    crawler = MoitCrawler(session=mock_session)
    articles = crawler.fetch_category_articles("thong-bao")
    assert len(articles) == 2

    art = crawler.fetch_article("https://moit.gov.vn/sample.html")
    assert art is not None
    assert art["doc_number"] == "1882/QĐ-BCT"
