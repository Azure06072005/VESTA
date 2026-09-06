"""Unit tests cho bộ cào chính sách & công văn hiệp hội VBA (vba_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.vba_crawler import (
    parse_vba_datetime,
    extract_vba_doc_metadata,
    build_vba_page_url,
    parse_vba_listing,
    parse_vba_article_record,
    write_vba_macro_policy,
)

SAMPLE_VBA_LISTING_HTML = """
<div class="wrap-blog-item-main">
  <div class="item-blog-2">
    <div class="box-text">
      <h3 class="title font-bold">
        <a href="https://vba.com.vn/vba-gop-y-du-thao-luat-thue-tieu-thu-dac-biet.html">
          VBA góp ý Dự thảo Luật Thuế tiêu thụ đặc biệt đối với đồ uống có cồn
        </a>
      </h3>
    </div>
  </div>
  <div class="item-blog-2">
    <div class="box-text">
      <h3 class="title font-bold">
        <a href="/cong-van-73-cv-vba-ve-an-toan-thuc-pham.html">
          Công văn số 73/CV-VBA về giảm tiền kiểm an toàn thực phẩm
        </a>
      </h3>
    </div>
  </div>
  <div class="item-blog-2">
    <div class="box-text">
      <a href="/gioi-thieu.html">Giới thiệu (Bỏ qua vì không phải bài viết)</a>
    </div>
  </div>
</div>
"""

SAMPLE_VBA_ARTICLE_HTML = """
<html>
<head><title>VBA góp ý Dự thảo Luật Thuế TTĐB - VBA</title></head>
<body>
  <div class="box-title-main">
    VBA góp ý Dự thảo Luật Thuế tiêu thụ đặc biệt: Đề xuất lộ trình tăng thuế phù hợp
  </div>
  <div class="wrap-share view-header">
    10/08/2026 - 10:16 PM 61 lượt xem
  </div>
  <div class="wrap-blog-detail-main">
    <p>Hiệp hội Bia – Rượu – Nước giải khát Việt Nam (VBA) có Công văn số 73/CV-VBA gửi Bộ Tài chính và Chính phủ.</p>
    <p>VBA kiến nghị xem xét lộ trình áp thuế tiêu thụ đặc biệt đối với nước giải khát có đường và bia rượu,
    nhằm hỗ trợ phục hồi sản xuất kinh doanh cho các doanh nghiệp lớn như Sabeco (SAB) và Habeco (BHN),
    tránh gây sốc giá tiêu dùng và ảnh hưởng đến chuỗi cung ứng thực phẩm đồ uống.</p>
  </div>
</body>
</html>
"""


def test_parse_vba_datetime():
    parsed = parse_vba_datetime("10/08/2026 - 10:16 PM")
    assert parsed.year == 2026
    assert parsed.month == 8
    assert parsed.day == 10
    # 22:16 PM giờ VN (UTC+7) tương ứng 15:16 UTC
    assert parsed.hour == 15
    assert parsed.minute == 16

    parsed_date_only = parse_vba_datetime("15/05/2025")
    assert parsed_date_only.year == 2025
    assert parsed_date_only.month == 5
    assert parsed_date_only.day == 15


def test_extract_vba_doc_metadata_excise_tax():
    headline = "VBA góp ý Dự thảo Luật Thuế tiêu thụ đặc biệt đối với nước giải khát có đường"
    doc_type, doc_num, issuing = extract_vba_doc_metadata(headline)
    assert doc_type == "Kiến nghị thuế tiêu thụ đặc biệt"
    assert issuing == "Hiệp hội Bia - Rượu - Nước giải khát Việt Nam (VBA)"


def test_extract_vba_doc_metadata_dispatch():
    headline = "Công văn 73/CV-VBA gửi Bộ Y tế về quy chuẩn chất lượng đồ uống"
    doc_type, doc_num, issuing = extract_vba_doc_metadata(headline)
    assert doc_type == "Công văn kiến nghị VBA"
    assert doc_num == "73/CV-VBA"
    assert issuing == "Hiệp hội Bia - Rượu - Nước giải khát Việt Nam (VBA)"


def test_extract_vba_doc_metadata_enterprise():
    headline = "Sabeco (SAB) công bố kết quả kinh doanh tăng trưởng và định hướng xuất khẩu"
    doc_type, doc_num, issuing = extract_vba_doc_metadata(headline)
    assert doc_type == "Tin tức doanh nghiệp đồ uống"


def test_build_vba_page_url():
    url_p1 = build_vba_page_url("chinh-sach-1", 1)
    assert url_p1 == "https://vba.com.vn/chinh-sach-1.html"

    url_p2 = build_vba_page_url("chinh-sach-1", 2)
    assert url_p2 == "https://vba.com.vn/chinh-sach-1/p-2.html"


def test_parse_vba_listing():
    articles = parse_vba_listing(SAMPLE_VBA_LISTING_HTML)
    assert len(articles) == 2
    assert "Thuế tiêu thụ đặc biệt" in articles[0]["title"]
    assert "73/CV-VBA" in articles[1]["title"]
    assert articles[0]["url"].startswith("https://vba.com.vn/")


def test_parse_vba_article_record():
    url = "https://vba.com.vn/vba-gop-y-du-thao-luat-thue-tieu-thu-dac-biet.html"
    record = parse_vba_article_record(SAMPLE_VBA_ARTICLE_HTML, url)
    assert record is not None
    assert record["source"] == "vba"
    assert record["issuing_body"] == "Hiệp hội Bia - Rượu - Nước giải khát Việt Nam (VBA)"
    assert record["doc_type"] == "Công văn kiến nghị VBA" or record["doc_type"] == "Kiến nghị thuế tiêu thụ đặc biệt"
    assert record["doc_number"] == "73/CV-VBA"
    assert "Sabeco" in record["body"]
    assert record["source_url"] == url


def test_write_vba_macro_policy_idempotency():
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
        "source": "vba",
        "issuing_body": "Hiệp hội Bia - Rượu - Nước giải khát Việt Nam (VBA)",
        "doc_type": "Công văn kiến nghị VBA",
        "doc_number": "73/CV-VBA",
        "published_at": now,
        "available_at": now,
        "headline": "Kiến nghị thuế TTĐB",
        "summary": "Tóm tắt",
        "body": "Nội dung kiến nghị của VBA",
        "source_url": "https://vba.com.vn/kien-nghi-thue.html",
        "fetched_at": now,
    }]
    df = pd.DataFrame(data)

    n1 = write_vba_macro_policy(con, df)
    assert n1 == 1

    # Chạy lần 2 ghi cùng source_url -> không làm duplicate core
    n2 = write_vba_macro_policy(con, df)
    count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    assert count == 1
