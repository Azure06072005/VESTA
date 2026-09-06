"""Bộ kiểm thử đơn vị cho nda_crawler.py (Hiệp hội Dữ liệu Quốc gia)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.crawlers.nda_crawler import (
    clean_html_text,
    extract_nda_doc_metadata,
    parse_nda_api_item,
    parse_nda_datetime,
    write_nda_macro_policy,
)


def test_parse_nda_datetime_iso():
    """Kiểm tra bóc tách ngày dạng ISO datetime."""
    iso_str = "2026-09-04T10:10:23.9398549"
    parsed = parse_nda_datetime(iso_str)
    assert parsed.year == 2026
    assert parsed.month == 9
    assert parsed.day == 4
    assert parsed.tzinfo == dt.timezone.utc


def test_parse_nda_datetime_slash():
    """Kiểm tra bóc tách ngày dạng dd/mm/yyyy."""
    date_str = "28/08/2026"
    parsed = parse_nda_datetime(date_str)
    assert parsed.year == 2026
    assert parsed.month == 8
    assert parsed.day == 28


def test_extract_nda_doc_metadata_data_center():
    """Kiểm tra phân loại trung tâm dữ liệu, điện toán đám mây và mã FPT, CTR."""
    headline = "Phát triển hạ tầng trung tâm dữ liệu và Cloud phục vụ cơ sở dữ liệu quốc gia"
    body = "Các doanh nghiệp công nghệ lớn như FPT và CTR đẩy mạnh đầu tư Data Center đạt chuẩn Tier 3."
    doc_type, doc_num, issuing_body = extract_nda_doc_metadata(headline, body)

    assert doc_type == "Hạ tầng trung tâm dữ liệu & điện toán đám mây"
    assert doc_num is None
    assert issuing_body == "Hiệp hội Dữ liệu Quốc gia"


def test_extract_nda_doc_metadata_decree():
    """Kiểm tra bóc tách số hiệu Nghị định 47/2024/NĐ-CP và cơ quan ban hành Chính phủ."""
    headline = "Nghị định 47/2024/NĐ-CP quy định về danh mục cơ sở dữ liệu quốc gia"
    body = "Chính phủ vừa ban hành Nghị định 47/2024/NĐ-CP nhằm chuẩn hóa việc kết nối dữ liệu."
    doc_type, doc_num, issuing_body = extract_nda_doc_metadata(headline, body)

    assert doc_type == "Quy chuẩn kết nối & đồng bộ dữ liệu quốc gia"
    assert doc_num == "47/2024/NĐ-CP"
    assert issuing_body == "Chính phủ"


def test_clean_html_text():
    """Kiểm tra làm sạch thẻ HTML, mã hóa ký tự và loại bỏ script."""
    raw = "<p>Dữ liệu &amp; an to&agrave;n th&ocirc;ng tin</p><script>alert(1);</script>"
    cleaned = clean_html_text(raw)
    assert "Dữ liệu & an toàn thông tin" in cleaned
    assert "alert" not in cleaned


def test_parse_nda_api_item():
    """Kiểm tra bóc tách một item từ payload JSON NDA API."""
    raw_item = {
        "id": "84129aee-ec3c-487a-8b5c-c98856d45c8e",
        "tile": "8/12 CSDL quốc gia hoàn thành kết nối dữ liệu",
        "link": "8-12-csdl-quoc-gia-hoan-thanh-ket-noi",
        "description": "Chiến dịch 100 ngày cao điểm kết nối cơ sở dữ liệu quốc gia.",
        "publishDate": "2026-09-04T10:10:23.9398549",
        "content": "<p>Đã có 8/12 cơ sở dữ liệu quốc gia hoàn thành kết nối đồng bộ theo Đề án 06.</p>",
    }
    rec = parse_nda_api_item(raw_item)

    assert rec is not None
    assert rec["source"] == "nda"
    assert "8/12 CSDL quốc gia hoàn thành kết nối" in rec["headline"]
    assert "Chiến dịch 100 ngày" in rec["summary"]
    assert "Đề án 06" in rec["body"]
    assert "https://nda.org.vn/bai-viet/8-12-csdl-quoc-gia-hoan-thanh-ket-noi" == rec["source_url"]


def test_write_nda_macro_policy_idempotency():
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
            "source": "nda",
            "issuing_body": "Hiệp hội Dữ liệu Quốc gia",
            "doc_type": "Quy chuẩn kết nối & đồng bộ dữ liệu quốc gia",
            "doc_number": "47/2024/NĐ-CP",
            "published_at": now,
            "available_at": now,
            "headline": "Tiêu chuẩn kết nối trung tâm dữ liệu quốc gia 2026",
            "summary": "Tóm tắt tiêu chuẩn kỹ thuật kết nối dữ liệu quốc gia",
            "body": "Chi tiết quy chuẩn kỹ thuật an toàn thông tin...",
            "source_url": "https://nda.org.vn/bai-viet/tieu-chuan-csdl-2026",
            "fetched_at": now,
        }
    ])

    written_1 = write_nda_macro_policy(con, df)
    assert written_1 == 1

    # Ghi trùng lặp
    written_2 = write_nda_macro_policy(con, df)
    assert written_2 == 0

    core_count = con.execute("SELECT COUNT(*) FROM core.macro_policy").fetchone()[0]
    assert core_count == 1
