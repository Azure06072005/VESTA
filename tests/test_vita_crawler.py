"""Unit tests cho bộ cào chính sách & dữ liệu du lịch VITA (vita_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.vita_crawler import (
    parse_vita_date,
    extract_vita_doc_metadata,
    build_vita_page_url,
    parse_vita_listing,
    parse_vita_article_record,
    write_vita_macro_policy,
)

SAMPLE_VITA_LISTING_HTML = """
<div class="news-list">
  <div class="item">
    <a href="/vi/news/de-xuat-mo-rong-chinh-sach-mien-thi-thuc-visa-280.html">
      Đề xuất mở rộng chính sách miễn thị thực visa đón làn sóng khách quốc tế
    </a>
  </div>
  <div class="item">
    <a href="/vi/news/thong-ke-luong-khach-quoc-te-tang-truong-an-tuong-275.html">
      Thống kê lượng khách quốc tế và hàng không tăng trưởng ấn tượng trong 8 tháng
    </a>
  </div>
  <div class="item">
    <a href="/vi/about.html">
      Giới thiệu (Bỏ qua vì không phải bài viết tin tức)
    </a>
  </div>
</div>
"""

SAMPLE_VITA_ARTICLE_HTML = """
<html>
<head><title>Đề xuất mở rộng chính sách miễn thị thực visa - VITA</title></head>
<body>
  <div class="media-content-body">
    <h1>Đề xuất mở rộng chính sách miễn thị thực visa đón làn sóng khách du lịch quốc tế</h1>
    <span class="date">19/10/2025</span>
    <div class="media-content">
      <p>Hiệp hội Du lịch Việt Nam (VITA) vừa có văn bản gửi Thủ tướng Chính phủ kiến nghị mở rộng danh sách các quốc gia được miễn thị thực.</p>
      <p>Động thái này được kỳ vọng sẽ tạo động lực tăng trưởng mạnh mẽ cho các hãng hàng không nội địa như Vietnam Airlines (HVN)
      và Vietjet Air (VJC), đồng thời thúc đẩy công suất phòng của hệ thống khách sạn và khu nghỉ dưỡng ven biển.</p>
    </div>
  </div>
</body>
</html>
"""


def test_parse_vita_date():
    parsed = parse_vita_date("19/10/2025")
    assert parsed.year == 2025
    assert parsed.month == 10
    assert parsed.day == 19

    parsed_dash = parse_vita_date("05-08-2026")
    assert parsed_dash.year == 2026
    assert parsed_dash.month == 8
    assert parsed_dash.day == 5


def test_extract_vita_doc_metadata_visa():
    headline = "Kiến nghị kéo dài thời hạn tạm trú và mở rộng diện miễn visa du lịch"
    doc_type, doc_num, issuing = extract_vita_doc_metadata(headline)
    assert doc_type == "Chính sách visa & xuất nhập cảnh"
    assert issuing == "Hiệp hội Du lịch Việt Nam (VITA)"


def test_extract_vita_doc_metadata_aviation():
    headline = "Thống kê lượng khách quốc tế và các chuyến bay của Vietjet (VJC) tăng mạnh"
    doc_type, doc_num, issuing = extract_vita_doc_metadata(headline)
    assert doc_type == "Thống kê lượng khách du lịch & hàng không"


def test_extract_vita_doc_metadata_general():
    headline = "Hội chợ Du lịch Quốc tế Việt Nam - VITM Hà Nội thu hút hàng trăm doanh nghiệp"
    doc_type, doc_num, issuing = extract_vita_doc_metadata(headline)
    assert doc_type == "Hoạt động xúc tiến & thị trường du lịch"


def test_build_vita_page_url():
    url_p1 = build_vita_page_url("news", 1)
    assert url_p1 == "https://vita.vn/vi/news.html"

    url_p2 = build_vita_page_url("news", 2)
    assert "page=9" in url_p2

    url_p3 = build_vita_page_url("news", 3)
    assert "page=18" in url_p3


def test_parse_vita_listing():
    articles = parse_vita_listing(SAMPLE_VITA_LISTING_HTML)
    assert len(articles) == 2
    assert "thị thực visa" in articles[0]["title"]
    assert "khách quốc tế" in articles[1]["title"]
    assert articles[0]["url"].startswith("https://vita.vn/vi/news/")


def test_parse_vita_article_record():
    url = "https://vita.vn/vi/news/de-xuat-mien-visa-280.html"
    record = parse_vita_article_record(SAMPLE_VITA_ARTICLE_HTML, url)
    assert record is not None
    assert record["source"] == "vita"
    assert record["issuing_body"] == "Hiệp hội Du lịch Việt Nam (VITA)"
    assert record["doc_type"] == "Chính sách visa & xuất nhập cảnh"
    assert record["published_at"].year == 2025
    assert "Vietnam Airlines" in record["body"]
    assert record["source_url"] == url


def test_write_vita_macro_policy_idempotency():
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
        "source": "vita",
        "issuing_body": "Hiệp hội Du lịch Việt Nam (VITA)",
        "doc_type": "Chính sách visa & xuất nhập cảnh",
        "doc_number": None,
        "published_at": now,
        "available_at": now,
        "headline": "Kiến nghị mở rộng miễn visa",
        "summary": "Tóm tắt",
        "body": "Nội dung kiến nghị của VITA",
        "source_url": "https://vita.vn/vi/news/test-visa.html",
        "fetched_at": now,
    }]
    df = pd.DataFrame(data)

    n1 = write_vita_macro_policy(con, df)
    assert n1 == 1

    # Chạy lần 2 ghi cùng source_url -> không làm duplicate core
    n2 = write_vita_macro_policy(con, df)
    count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    assert count == 1
