"""Unit tests cho Ủy ban Chứng khoán Nhà nước Crawler (ssc_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
from unittest.mock import MagicMock

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.ssc_crawler import (
    parse_ssc_datetime,
    extract_doc_number,
    extract_canonical_url,
    parse_category_soup,
    parse_article_soup,
    SscCrawler,
)

SAMPLE_CATEGORY_HTML = """
<html>
<body>
<div class="portlet-body">
    <ul>
        <li>
            <a href="/webcenter/portal/ubck/pages_r/l/chitittinttgs?dDocName=APPSSCGOVVN1620171049">
                Xử phạt vi phạm hành chính trong lĩnh vực chứng khoán đối với Công ty CP Dầu khí Nghệ An
            </a>
        </li>
        <li>
            <a href="/webcenter/portal/ubck/pages_r/l/chitittinttgs?dDocName=APPSSCGOVVN1620170862">
                Xử phạt vi phạm hành chính đối với ông Nguyễn Văn A do thao túng thị trường chứng khoán
            </a>
        </li>
        <!-- Bad link without dDocName -->
        <li>
            <a href="/webcenter/portal/ubck/pages_r/m/tintc-skin">Trang tin tức</a>
        </li>
    </ul>
</div>
</body>
</html>
"""

SAMPLE_ARTICLE_HTML = """
<html>
<body>
<div class="detail-container">
    <div class="new-content cd-content">
        <h1 class="detail-title">
            Xử phạt vi phạm hành chính trong lĩnh vực chứng khoán và thị trường chứng khoán đối với Công ty cổ phần Đầu tư Dầu khí
            <small><i class="far fa-clock mr-1"></i>04/09/2026</small>
        </h1>
        <p>Ngày 04/9/2026, Ủy ban Chứng khoán Nhà nước ban hành Quyết định số 285/QĐ-XPHC về việc xử phạt vi phạm hành chính.</p>
        <p>Phạt tiền 150.000.000 đồng theo quy định tại điểm a khoản 3 Điều 42 Nghị định số 156/2020/NĐ-CP.</p>
        <p>Quyết định có hiệu lực kể từ ngày ký.</p>
    </div>
</div>
</body>
</html>
"""


def test_parse_ssc_datetime():
    """Kiểm tra chuyển đổi thời gian SSC sang UTC."""
    parsed = parse_ssc_datetime("04/09/2026")
    assert parsed.year == 2026
    assert parsed.month == 9
    assert parsed.day == 3  # 00:00 ICT - 7h = 17:00 UTC ngày hôm trước
    assert parsed.hour == 17

    parsed_time = parse_ssc_datetime("04/09/2026 14:30")
    assert parsed_time.year == 2026
    assert parsed_time.month == 9
    assert parsed_time.day == 4
    assert parsed_time.hour == 7  # 14 - 7


def test_extract_doc_number():
    """Kiểm tra trích xuất số quyết định xử phạt vi phạm chứng khoán."""
    assert extract_doc_number("Thông báo", "Theo Quyết định số 285/QĐ-XPHC ngày 04/9", "") == "285/QĐ-XPHC"
    assert extract_doc_number("Ban hành Nghị định số 156/2020/NĐ-CP", "", "") == "156/2020/NĐ-CP"
    assert extract_doc_number("Bài viết chung", "Không có số văn bản", "") is None


def test_extract_canonical_url():
    """Kiểm tra chuẩn hóa URL theo mã định danh dDocName."""
    raw = "/webcenter/portal/ubck/pages_r/l/chitittinttgs?dDocName=APPSSCGOVVN1620171049&extra=123"
    canonical = extract_canonical_url(raw)
    assert canonical == "https://ssc.gov.vn/webcenter/portal/ubck/pages_r/l/chitittinttgs?dDocName=APPSSCGOVVN1620171049"


def test_parse_category_soup():
    """Kiểm tra trích xuất danh sách link bài viết từ trang danh mục SSC."""
    articles = parse_category_soup(SAMPLE_CATEGORY_HTML, "thanhtra-gimst")
    assert len(articles) == 2
    assert "APPSSCGOVVN1620171049" in articles[0]["url"]
    assert "Dầu khí Nghệ An" in articles[0]["title"]
    assert "APPSSCGOVVN1620170862" in articles[1]["url"]


def test_parse_article_soup():
    """Kiểm tra bóc tách chi tiết quyết định xử phạt từ HTML trang chi tiết."""
    url = "https://ssc.gov.vn/webcenter/portal/ubck/pages_r/l/chitittinttgs?dDocName=APPSSCGOVVN1620171049"
    rec = parse_article_soup(SAMPLE_ARTICLE_HTML, url)
    assert rec is not None
    assert rec["source"] == "ssc"
    assert rec["issuing_body"] == "Ủy ban Chứng khoán Nhà nước (UBCKNN)"
    assert rec["doc_type"] == "Quyết định xử phạt vi phạm chứng khoán"
    assert rec["doc_number"] == "285/QĐ-XPHC"
    assert "Dầu khí" in rec["headline"]
    assert "150.000.000 đồng" in rec["body"]
    assert rec["source_url"] == url


def test_save_to_database(tmp_path):
    """Kiểm tra lưu dữ liệu vào DuckDB với kiểm soát khóa chính và upsert."""
    db_file = str(tmp_path / "test_ssc.duckdb")
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

    crawler = SscCrawler(db_path=db_file)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    records = [
        {
            "source": "ssc",
            "issuing_body": "Ủy ban Chứng khoán Nhà nước (UBCKNN)",
            "doc_type": "Quyết định xử phạt vi phạm chứng khoán",
            "doc_number": "285/QĐ-XPHC",
            "published_at": now,
            "available_at": now,
            "headline": "Quyết định xử phạt 1",
            "summary": "Tóm tắt 1",
            "body": "Nội dung 1",
            "source_url": "https://ssc.gov.vn/webcenter/portal/ubck/pages_r/l/chitit?dDocName=APPSSC1",
            "fetched_at": now,
        },
        {
            "source": "ssc",
            "issuing_body": "Ủy ban Chứng khoán Nhà nước (UBCKNN)",
            "doc_type": "Chỉ đạo điều hành UBCKNN",
            "doc_number": None,
            "published_at": now,
            "available_at": now,
            "headline": "Thông báo 2",
            "summary": "Tóm tắt 2",
            "body": "Nội dung 2",
            "source_url": "https://ssc.gov.vn/webcenter/portal/ubck/pages_r/l/chitit?dDocName=APPSSC2",
            "fetched_at": now,
        },
    ]

    saved = crawler.save_to_database(records)
    assert saved == 2

    # Verify contents
    check_conn = duckdb.connect(db_file, read_only=True)
    assert check_conn.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'ssc'").fetchone()[0] == 2
    check_conn.close()

    # Test idempotency on re-insertion
    saved_again = crawler.save_to_database(records)
    assert saved_again == 2
    check_conn2 = duckdb.connect(db_file, read_only=True)
    assert check_conn2.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'ssc'").fetchone()[0] == 2
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

    crawler = SscCrawler(session=mock_session)
    pages = crawler.fetch_category_page("thanhtra-gimst", page=1)
    assert len(pages) == 2

    article = crawler.fetch_article("https://ssc.gov.vn/webcenter/portal/ubck/pages_r/l/chitittinttgs?dDocName=APPSSCGOVVN1620171049")
    assert article is not None
    assert article["doc_number"] == "285/QĐ-XPHC"
