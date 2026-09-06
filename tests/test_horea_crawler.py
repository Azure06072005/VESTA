"""Unit tests cho bộ cào chính sách & công văn bất động sản HoREA (horea_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.horea_crawler import (
    parse_horea_date,
    extract_horea_doc_metadata,
    build_horea_page_url,
    parse_horea_listing,
    parse_horea_article_record,
    write_horea_macro_policy,
)

SAMPLE_HOREA_LISTING_HTML = """
<div class="main-content">
  <div class="item">
    <a href="/hoat-dong-horea/Cong-van-1102026CV-HoREA-ngay-03-thang-09-nam-2026.html">
      Công văn 110/2026/CV-HoREA ngày 03 tháng 09 năm 2026 Đề xuất hoàn thiện chính sách pháp luật BĐS
    </a>
  </div>
  <div class="item">
    <a href="/hoat-dong-horea/Van-ban-1042026CV-HoREA-ngay-28-thang-08-nam-2026.html">
      Văn bản 104/2026/CV-HoREA ngày 28 tháng 08 năm 2026 Đề cử doanh nhân tiêu biểu
    </a>
  </div>
  <div class="item">
    <a href="/gioi-thieu/Ban-chap-hanh.html">
      Ban chấp hành nhiệm kỳ (Bỏ qua link không thuộc chuyên mục)
    </a>
  </div>
</div>
"""

SAMPLE_HOREA_ARTICLE_HTML = """
<html>
<head><title>Công văn 110/2026/CV-HoREA - HOREA</title></head>
<body>
  <h1>Công văn 110/2026/CV-HoREA ngày 03 tháng 09 năm 2026 Đề xuất tháo gỡ vướng mắc dự án bất động sản</h1>
  <div class="date">Ngày đăng: 03-09-2026</div>
  <div class="content_general">
    <p>Hiệp hội Bất động sản TP.HCM kính gửi Thủ tướng Chính phủ và Bộ Xây dựng kiến nghị tháo gỡ khó khăn cho các dự án.</p>
    <p>HoREA đề xuất xem xét điều chỉnh các quy định về kinh doanh công trình xây dựng có công năng hỗn hợp, căn hộ du lịch,
    nhằm khơi thông nguồn vốn tín dụng và thanh khoản cho các chủ đầu tư bất động sản niêm yết trên thị trường chứng khoán.</p>
  </div>
</body>
</html>
"""


def test_parse_horea_date():
    parsed = parse_horea_date("Ngày đăng: 03-09-2026")
    assert parsed.year == 2026
    assert parsed.month == 9
    assert parsed.day == 3

    parsed_slash = parse_horea_date("TP.HCM, ngày 12/08/2026")
    assert parsed_slash.year == 2026
    assert parsed_slash.month == 8
    assert parsed_slash.day == 12


def test_extract_horea_doc_metadata_dispatch():
    headline = "Công văn 110/2026/CV-HoREA ngày 03 tháng 09 năm 2026 Đề xuất chính sách"
    doc_type, doc_num, issuing = extract_horea_doc_metadata(headline)
    assert doc_type == "Công văn kiến nghị BĐS"
    assert doc_num == "110/2026/CV-HoREA"
    assert issuing == "Hiệp hội Bất động sản TP.HCM (HoREA)"


def test_extract_horea_doc_metadata_unblocking():
    headline = "HoREA đề xuất giải pháp cấp bách tháo gỡ vướng mắc cho 156 dự án bất động sản"
    doc_type, doc_num, issuing = extract_horea_doc_metadata(headline)
    assert doc_type == "Tháo gỡ pháp lý dự án BĐS"
    assert issuing == "Hiệp hội Bất động sản TP.HCM (HoREA)"


def test_extract_horea_doc_metadata_land_law():
    headline = "Góp ý dự thảo Nghị định hướng dẫn thi hành Luật Đất đai 2024"
    doc_type, doc_num, issuing = extract_horea_doc_metadata(headline)
    assert doc_type == "Góp ý sửa đổi Luật BĐS"


def test_build_horea_page_url():
    url_p1 = build_horea_page_url("hoat-dong-horea", 1)
    assert url_p1 == "https://www.horea.org.vn/hoat-dong-horea.html"

    url_p3 = build_horea_page_url("hoat-dong-horea", 3)
    assert url_p3 == "https://www.horea.org.vn/hoat-dong-horea/pages-3.html"


def test_parse_horea_listing():
    articles = parse_horea_listing(SAMPLE_HOREA_LISTING_HTML, "hoat-dong-horea")
    assert len(articles) == 2
    assert "110/2026/CV-HoREA" in articles[0]["title"]
    assert "104/2026/CV-HoREA" in articles[1]["title"]
    assert articles[0]["url"].startswith("https://www.horea.org.vn/hoat-dong-horea/")


def test_parse_horea_article_record():
    url = "https://www.horea.org.vn/hoat-dong-horea/Cong-van-1102026CV-HoREA.html"
    record = parse_horea_article_record(SAMPLE_HOREA_ARTICLE_HTML, url)
    assert record is not None
    assert record["source"] == "horea"
    assert record["issuing_body"] == "Hiệp hội Bất động sản TP.HCM (HoREA)"
    assert record["doc_type"] == "Công văn kiến nghị BĐS"
    assert record["doc_number"] == "110/2026/CV-HoREA"
    assert "tháo gỡ khó khăn cho các dự án" in record["body"]
    assert record["source_url"] == url


def test_write_horea_macro_policy_idempotency():
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
        "source": "horea",
        "issuing_body": "Hiệp hội Bất động sản TP.HCM (HoREA)",
        "doc_type": "Công văn kiến nghị BĐS",
        "doc_number": "110/2026/CV-HoREA",
        "published_at": now,
        "available_at": now,
        "headline": "Công văn kiến nghị tháo gỡ dự án",
        "summary": "Tóm tắt",
        "body": "Nội dung kiến nghị của HoREA",
        "source_url": "https://www.horea.org.vn/hoat-dong-horea/cv-110.html",
        "fetched_at": now,
    }]
    df = pd.DataFrame(data)

    n1 = write_horea_macro_policy(con, df)
    assert n1 == 1

    # Chạy lần 2 cùng source_url -> không làm duplicate core
    n2 = write_horea_macro_policy(con, df)
    count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    assert count == 1
