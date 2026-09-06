"""Unit tests cho bộ cào chính sách tiền tệ Ngân hàng Nhà nước Việt Nam (sbv_crawler.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.sbv_crawler import (
    clean_article_url,
    parse_vietnamese_datetime,
    extract_sbv_doc_metadata,
    check_is_waf_rejected,
    parse_sbv_news_listing,
    parse_sbv_article_record,
    write_sbv_macro_policy,
    build_page_url,
)

SAMPLE_LISTING_HTML = """
<div class="portlet-content">
  <div class="col-sm-8">
    <span class="date-about"><i>26/08/2026 | 13:35:00</i></span>
    <a class="title-news-link" href="https://sbv.gov.vn/vi/w/408.000-ty-dong-san-sang-tiep-suc?redirect=%2Fvi%2Ftin-tuc-su-kien">
      <span class="title-news"><b><h6>408.000 tỷ đồng sẵn sàng tiếp sức cho nền kinh tế</h6></b></span>
    </a>
  </div>
  <div class="col-sm-8">
    <span class="date-about"><i>20/08/2026</i></span>
    <a class="title-news-link" href="/vi/w/thong-tu-02-2023-tt-nhnn-ve-co-cau-lai-thoi-han-tra-no">
      <span class="title-news"><b><h6>Ban hành Thông tư 02/2023/TT-NHNN cơ cấu lại thời hạn trả nợ</h6></b></span>
    </a>
  </div>
</div>
"""

SAMPLE_ARTICLE_HTML = """
<html>
<head><title>Chi tiết văn bản điều hành - NHNN</title></head>
<body>
  <h1>Ngân hàng Nhà nước điều chỉnh các mức lãi suất điều hành</h1>
  <div class="date-about"><i>15/06/2026 | 09:00:00</i></div>
  <div class="sapo">NHNN ban hành Quyết định 1125/QĐ-NHNN về lãi suất tái cấp vốn.</div>
  <div class="journal-content-article">
    Ngày 15/06/2026, Thống đốc Ngân hàng Nhà nước Việt Nam đã ký ban hành Quyết định 1125/QĐ-NHNN
    về việc điều chỉnh giảm lãi suất tái cấp vốn từ 5.0%/năm xuống 4.5%/năm nhằm hỗ trợ tăng trưởng kinh tế,
    tháo gỡ khó khăn cho doanh nghiệp và người dân theo chỉ đạo của Chính phủ và Thủ tướng Chính phủ.
    Quyết định này có hiệu lực thi hành kể từ ngày ký.
  </div>
</body>
</html>
"""

SAMPLE_WAF_REJECTED_HTML = """
<html><head><title>Request Rejected</title></head><body>The requested URL was rejected. Please consult with your administrator.<br><br>Your support ID is: <4409962095056716331><br><br><a href='javascript:history.back();'>[Go Back]</body></html>
"""


def test_clean_article_url():
    raw = "https://sbv.gov.vn/vi/w/bai-viet-cstt?redirect=%2Fvi%2Ftin-tuc-su-kien&utm_source=test"
    cleaned = clean_article_url(raw)
    assert cleaned == "https://sbv.gov.vn/vi/w/bai-viet-cstt"
    assert "redirect" not in cleaned


def test_parse_vietnamese_datetime():
    # Có ngày giờ đầy đủ
    parsed = parse_vietnamese_datetime("26/08/2026 | 13:35:00")
    assert parsed.year == 2026
    assert parsed.month == 8
    assert parsed.day == 26
    # 13:35:00 giờ Việt Nam (UTC+7) tương ứng 06:35:00 UTC
    assert parsed.hour == 6
    assert parsed.minute == 35

    # Chỉ có ngày
    parsed_date_only = parse_vietnamese_datetime("15/05/2025")
    assert parsed_date_only.year == 2025
    assert parsed_date_only.month == 5
    assert parsed_date_only.day == 14 or parsed_date_only.day == 15


def test_extract_sbv_doc_metadata_circular():
    headline = "Thống đốc ban hành Thông tư 02/2023/TT-NHNN hỗ trợ doanh nghiệp"
    doc_type, doc_num, issuing = extract_sbv_doc_metadata(headline)
    assert doc_type == "Thông tư"
    assert doc_num == "02/2023/TT-NHNN"
    assert issuing == "Ngân hàng Nhà nước Việt Nam"


def test_extract_sbv_doc_metadata_decision():
    headline = "Quyết định 1125/QĐ-NHNN về việc hạ lãi suất điều hành"
    doc_type, doc_num, issuing = extract_sbv_doc_metadata(headline)
    assert doc_type == "Quyết định"
    assert doc_num == "1125/QĐ-NHNN"
    assert issuing == "Ngân hàng Nhà nước Việt Nam"


def test_extract_sbv_doc_metadata_prime_minister():
    headline = "Chỉ thị 15/CT-TTg về đẩy mạnh tháo gỡ khó khăn tín dụng ngân hàng"
    doc_type, doc_num, issuing = extract_sbv_doc_metadata(headline)
    assert doc_type == "Chỉ thị"
    assert doc_num == "15/CT-TTG"
    assert issuing == "Thủ tướng Chính phủ"


def test_check_is_waf_rejected():
    assert check_is_waf_rejected(SAMPLE_WAF_REJECTED_HTML) is True
    assert check_is_waf_rejected(SAMPLE_ARTICLE_HTML) is False


def test_parse_sbv_news_listing():
    articles = parse_sbv_news_listing(SAMPLE_LISTING_HTML)
    assert len(articles) == 2
    assert "408.000 tỷ đồng" in articles[0]["title"]
    assert "redirect" not in articles[0]["url"]
    assert articles[0]["date_str"] == "26/08/2026 | 13:35:00"
    assert "02/2023/TT-NHNN" in articles[1]["title"]


def test_parse_sbv_article_record():
    url = "https://sbv.gov.vn/vi/w/quyet-dinh-1125-qd-nhnn"
    record = parse_sbv_article_record(SAMPLE_ARTICLE_HTML, url)
    assert record is not None
    assert record["source"] == "sbv"
    assert record["issuing_body"] == "Ngân hàng Nhà nước Việt Nam"
    assert record["doc_type"] == "Điều hành lãi suất" or record["doc_type"] == "Quyết định"
    assert record["doc_number"] == "1125/QĐ-NHNN"
    assert "lãi suất tái cấp vốn" in record["body"]
    assert record["source_url"] == url


def test_build_page_url():
    url = build_page_url(page=3, delta=20)
    assert "cur=3" in url
    assert "delta=20" in url
    assert "com_liferay_asset_publisher_web_portlet" in url


def test_write_sbv_macro_policy_idempotency():
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
        "source": "sbv",
        "issuing_body": "Ngân hàng Nhà nước Việt Nam",
        "doc_type": "Thông tư",
        "doc_number": "02/2023/TT-NHNN",
        "published_at": now,
        "available_at": now,
        "headline": "Thông tư cơ cấu lại nợ",
        "summary": "Tóm tắt",
        "body": "Nội dung đầy đủ của thông tư",
        "source_url": "https://sbv.gov.vn/vi/w/tt-02",
        "fetched_at": now,
    }]
    df = pd.DataFrame(data)

    n1 = write_sbv_macro_policy(con, df)
    assert n1 == 1

    # Chạy lần 2 ghi cùng source_url -> Phải không làm duplicate core
    n2 = write_sbv_macro_policy(con, df)
    count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    assert count == 1
