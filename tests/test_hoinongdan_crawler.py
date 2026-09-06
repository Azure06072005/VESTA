"""Unit tests cho bộ cào chính sách & văn bản điều hành Hội Nông dân VN (hoinongdan_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.hoinongdan_crawler import (
    parse_hnd_datetime,
    extract_hnd_doc_metadata,
    parse_steering_detail_record,
    parse_news_article_record,
    write_hnd_macro_policy,
)

SAMPLE_STEERING_DETAIL_HTML = """
<html>
<head><title>Chi tiết văn bản điều hành - HND</title></head>
<body>
  <h1>Công văn V/v cung cấp vật tư phân bón và con giống vụ mùa</h1>
  <div class="LibraryDetail">
    <table>
      <tr><td>Số ký hiệu văn bản</td><td>722- CV/VP</td></tr>
      <tr><td>Ngày ban hành</td><td>26/11/2024</td></tr>
      <tr><td>Ngày hiệu lực</td><td>26/11/2024</td></tr>
      <tr><td>Trích yếu nội dung</td><td>Công văn hướng dẫn bình ổn giá phân bón đạm, lân và cung ứng giống lúa</td></tr>
      <tr><td>Người ký duyệt</td><td>Chánh Văn phòng Trung ương Hội NDVN</td></tr>
    </table>
    <div class="content">
      Nội dung chi tiết về việc kết nối các hợp tác xã nông nghiệp với Tổng công ty Phân bón và Hóa chất Dầu khí (DPM)
      và Công ty Cổ phần Phân bón Dầu khí Cà Mau (DCM) để bảo đảm đủ phân bón chất lượng cao, giá ổn định cho nông dân.
    </div>
  </div>
</body>
</html>
"""

SAMPLE_NEWS_ARTICLE_HTML = """
<html>
<head><title>Dự thảo Luật Đất đai sửa đổi hỗ trợ tích tụ ruộng đất nông nghiệp</title></head>
<body>
  <div class="ContentBanner">
    <h1>Dự thảo Luật Đất đai sửa đổi tạo động lực phát triển nông nghiệp hàng hóa quy mô lớn</h1>
    <span class="date">Thứ Sáu, 28/08/2026 09:35</span>
    <div class="ArticleContent">
      <p>Hội thảo quốc gia về cơ chế chuyển đổi và tích tụ đất nông nghiệp nhằm thu hút doanh nghiệp đầu tư công nghệ cao.</p>
      <p>Các chuyên gia nhấn mạnh việc bảo đảm chuỗi cung ứng lúa gạo xuất khẩu và hỗ trợ các tập đoàn nông nghiệp lớn
      như PAN Group (PAN) và Lộc Trời (LTG) liên kết bao tiêu nông sản cho bà con nông dân.</p>
    </div>
  </div>
</body>
</html>
"""


def test_parse_hnd_datetime():
    parsed_date = parse_hnd_datetime("26/11/2024")
    assert parsed_date.year == 2024
    assert parsed_date.month == 11
    assert parsed_date.day == 26

    parsed_dt = parse_hnd_datetime("28/08/2026 09:35")
    assert parsed_dt.year == 2026
    assert parsed_dt.month == 8
    assert parsed_dt.day == 28
    # 09:35 UTC+7 tương ứng 02:35 UTC
    assert parsed_dt.hour == 2
    assert parsed_dt.minute == 35


def test_extract_hnd_doc_metadata_fertilizer():
    headline = "Bảo đảm nguồn cung phân bón ure và NPK cho vụ lúa Đông Xuân"
    doc_type, doc_num, issuing = extract_hnd_doc_metadata(headline)
    assert doc_type == "Chính sách phân bón & vật tư nông nghiệp"
    assert issuing == "Hội Nông dân Việt Nam"


def test_extract_hnd_doc_metadata_rice_export():
    headline = "Thúc đẩy liên kết chuỗi giá trị xuất khẩu lúa gạo chất lượng cao"
    doc_type, doc_num, issuing = extract_hnd_doc_metadata(headline)
    assert doc_type == "Chính sách xuất khẩu nông sản & lúa gạo"


def test_extract_hnd_doc_metadata_steering():
    headline = "Công văn hướng dẫn sản xuất"
    doc_type, doc_num, issuing = extract_hnd_doc_metadata(headline, raw_doc_number="722- CV/VP")
    assert doc_type == "Công văn điều hành nông nghiệp"
    assert doc_num == "722- CV/VP"


def test_parse_steering_detail_record():
    url = "http://www.hoinongdan.org.vn/?pageid=27218&p_steering=153"
    record = parse_steering_detail_record(SAMPLE_STEERING_DETAIL_HTML, url)
    assert record is not None
    assert record["source"] == "hoinongdan"
    assert record["issuing_body"] == "Hội Nông dân Việt Nam"
    assert record["doc_number"] == "722- CV/VP"
    assert record["published_at"].year == 2024
    assert "DPM" in record["body"] or "phân bón" in record["body"]
    assert record["source_url"] == url


def test_parse_news_article_record():
    url = "http://www.hoinongdan.org.vn/chinh-sach/du-thao-luat-dat-dai"
    record = parse_news_article_record(SAMPLE_NEWS_ARTICLE_HTML, url)
    assert record is not None
    assert record["source"] == "hoinongdan"
    assert record["issuing_body"] == "Hội Nông dân Việt Nam"
    assert record["published_at"].year == 2026
    assert "PAN Group" in record["body"] or "lúa gạo" in record["body"]
    assert record["source_url"] == url


def test_write_hnd_macro_policy_idempotency():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA staging;")
    con.execute("CREATE SCHEMA core;")
    con.execute(
        """
        CREATE TABLE staging.macro_policy (
            source VARCHAR, issuing_body VARCHAR, doc_type VARCHAR, doc_number VARCHAR,
            published_at TIMESTAMP, available_at TIMESTAMP, headline VARCHAR,
            summary VARCHAR, body VARCHAR, source_url VARCHAR, fetched_at TIMESTAMP
        );
        CREATE TABLE core.macro_policy (
            source VARCHAR, issuing_body VARCHAR, doc_type VARCHAR, doc_number VARCHAR,
            published_at TIMESTAMP, available_at TIMESTAMP, headline VARCHAR,
            summary VARCHAR, body VARCHAR, source_url VARCHAR, fetched_at TIMESTAMP,
            PRIMARY KEY (source_url)
        );
        """
    )

    now = dt.datetime.now(dt.timezone.utc)
    data = [{
        "source": "hoinongdan",
        "issuing_body": "Hội Nông dân Việt Nam",
        "doc_type": "Chính sách phân bón & vật tư nông nghiệp",
        "doc_number": "722- CV/VP",
        "published_at": now,
        "available_at": now,
        "headline": "Bảo đảm cung ứng phân bón",
        "summary": "Tóm tắt",
        "body": "Nội dung chỉ đạo của Hội Nông dân",
        "source_url": "http://www.hoinongdan.org.vn/test-doc",
        "fetched_at": now,
    }]
    df = pd.DataFrame(data)

    n1 = write_hnd_macro_policy(con, df)
    assert n1 == 1

    # Ghi lại bản ghi trùng lặp -> không làm tăng core
    n2 = write_hnd_macro_policy(con, df)
    count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    assert count == 1
