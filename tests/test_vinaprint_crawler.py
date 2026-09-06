"""Bộ kiểm thử đơn vị cho vinaprint_crawler.py (Hiệp hội In Việt Nam)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.crawlers.vinaprint_crawler import (
    build_vinaprint_page_url,
    extract_vinaprint_doc_metadata,
    parse_vinaprint_article_record,
    parse_vinaprint_date,
    write_vinaprint_macro_policy,
)


def test_parse_vinaprint_date_text():
    """Kiểm tra bóc tách ngày dạng 'ngày dd tháng mm năm yyyy'."""
    text = "Hội nghị được tổ chức vào ngày 16 tháng 07 năm 2026 tại Hà Nội"
    parsed = parse_vinaprint_date(text)
    assert parsed.year == 2026
    assert parsed.month == 7
    assert parsed.day == 16
    assert parsed.tzinfo == dt.timezone.utc


def test_parse_vinaprint_date_slash():
    """Kiểm tra bóc tách ngày dạng dd/mm/yyyy."""
    text = "Thông báo số 05 ban hành ngày 25/11/2025"
    parsed = parse_vinaprint_date(text)
    assert parsed.year == 2025
    assert parsed.month == 11
    assert parsed.day == 25


def test_extract_vinaprint_doc_metadata_packaging():
    """Kiểm tra phân loại thị trường bao bì, giấy carton và mã cổ phiếu DHC, HHP."""
    headline = "TỔNG KẾT THỊ TRƯỜNG GIẤY BAO BÌ CARTON NĂM 2026"
    body = "Nhu cầu tiêu thụ bao bì và nguyên liệu giấy carton tăng mạnh, hỗ trợ DHC và HHP."
    doc_type, doc_num, issuing_body = extract_vinaprint_doc_metadata(headline, body)

    assert doc_type == "Thị trường bao bì & nguyên liệu giấy"
    assert doc_num is None
    assert issuing_body == "Hiệp hội In Việt Nam"


def test_extract_vinaprint_doc_metadata_decree():
    """Kiểm tra bóc tách số hiệu Nghị định 60/2024/NĐ-CP và cơ quan Chính phủ."""
    headline = "TỔNG KẾT THI HÀNH NGHỊ ĐỊNH 60/2024/NĐ-CP QUY ĐỊNH HOẠT ĐỘNG IN"
    body = "Chính phủ vừa ban hành các nội dung trọng tâm thi hành Nghị định 60/2024/NĐ-CP."
    doc_type, doc_num, issuing_body = extract_vinaprint_doc_metadata(headline, body)

    assert doc_type == "Chính sách quản lý nhà nước về in ấn & bao bì"
    assert doc_num == "60/2024/NĐ-CP"
    assert issuing_body == "Chính phủ"


def test_build_vinaprint_page_url():
    """Kiểm tra sinh URL phân trang chuẩn vinaprint."""
    url_p1 = build_vinaprint_page_url("thi-truong---xu-huong-sp533", 1)
    assert url_p1 == "http://vinaprint.com.vn/thi-truong---xu-huong-sp533"

    url_p2 = build_vinaprint_page_url("thi-truong---xu-huong-sp533", 2)
    assert url_p2 == "http://vinaprint.com.vn/product/533/1/thi-truong---xu-huong.html"

    url_p3 = build_vinaprint_page_url("thi-truong---xu-huong-sp533", 3)
    assert url_p3 == "http://vinaprint.com.vn/product/533/2/thi-truong---xu-huong.html"


def test_parse_vinaprint_article_record():
    """Kiểm tra bóc tách bài viết từ HTML vinaprint giả lập."""
    sample_html = """
    <html>
        <body>
            <h2>PHÂN TÍCH THỊ TRƯỜNG GIẤY VÀ BAO BÌ NĂM 2026</h2>
            <div class="detail-j">
                <p>Nhu cầu nguyên liệu giấy cuộn công nghiệp và bao bì carton tăng trưởng 12% trong năm 2026.</p>
                <p>Doanh nghiệp thành viên cần lưu ý giá nhập khẩu nguyên liệu bột giấy để cân đối giá thành sản xuất.</p>
                <h5>Bài viết cùng danh mục</h5>
                <div class="row"><div>Bài viết khác</div></div>
            </div>
        </body>
    </html>
    """
    url = "http://vinaprint.com.vn/phan-tich-thi-truong-giay-ct1234"
    rec = parse_vinaprint_article_record(sample_html, url)

    assert rec is not None
    assert rec["source"] == "vinaprint"
    assert "PHÂN TÍCH THỊ TRƯỜNG GIẤY VÀ BAO BÌ" in rec["headline"]
    assert "nguyên liệu giấy cuộn" in rec["body"]
    assert "Bài viết cùng danh mục" not in rec["body"]
    assert rec["source_url"] == url


def test_write_vinaprint_macro_policy_idempotency():
    """Kiểm tra tính idempotent khi ghi bảng staging và core trong DuckDB."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA staging")
    con.execute("CREATE SCHEMA core")

    con.execute("""
    CREATE TABLE staging.macro_policy (
        source VARCHAR,
        issuing_body VARCHAR,
        doc_type VARCHAR,
        doc_number VARCHAR,
        published_at TIMESTAMPTZ,
        available_at TIMESTAMPTZ,
        headline VARCHAR,
        summary VARCHAR,
        body VARCHAR,
        source_url VARCHAR,
        fetched_at TIMESTAMPTZ
    )
    """)
    con.execute("""
    CREATE TABLE core.macro_policy (
        source VARCHAR,
        issuing_body VARCHAR,
        doc_type VARCHAR,
        doc_number VARCHAR,
        published_at TIMESTAMPTZ,
        available_at TIMESTAMPTZ,
        headline VARCHAR,
        summary VARCHAR,
        body VARCHAR,
        source_url VARCHAR PRIMARY KEY,
        fetched_at TIMESTAMPTZ
    )
    """)

    now = dt.datetime.now(dt.timezone.utc)
    df = pd.DataFrame([
        {
            "source": "vinaprint",
            "issuing_body": "Hiệp hội In Việt Nam",
            "doc_type": "Thị trường bao bì & nguyên liệu giấy",
            "doc_number": None,
            "published_at": now,
            "available_at": now,
            "headline": "Tiêu chuẩn kỹ thuật bao bì xuất khẩu 2026",
            "summary": "Tóm tắt tiêu chuẩn kỹ thuật bao bì carton xuất khẩu",
            "body": "Nội dung chi tiết tiêu chuẩn kỹ thuật đóng gói bao bì...",
            "source_url": "http://vinaprint.com.vn/tieu-chuan-bao-bi-ct9999",
            "fetched_at": now,
        }
    ])

    written_1 = write_vinaprint_macro_policy(con, df)
    assert written_1 == 1

    # Ghi trùng lặp URL
    written_2 = write_vinaprint_macro_policy(con, df)
    assert written_2 == 0

    core_count = con.execute("SELECT COUNT(*) FROM core.macro_policy").fetchone()[0]
    assert core_count == 1
