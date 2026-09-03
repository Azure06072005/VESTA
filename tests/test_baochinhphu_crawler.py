"""Unit tests for Báo Chính phủ Macro & Regulatory Policy Crawler."""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from crawlers.baochinhphu_crawler import (
    check_robots_allowed,
    extract_doc_metadata,
    parse_article_links,
    parse_article_record,
    write_macro_policy,
)


def test_check_robots_allowed_returns_true():
    assert check_robots_allowed("https://baochinhphu.vn/kinh-te.htm") is True


def test_extract_doc_metadata_nghi_quyet():
    headline = "Nghị quyết số 33/NQ-CP của Chính phủ: Một số giải pháp tháo gỡ và thúc đẩy thị trường BĐS"
    doc_type, doc_number, issuing_body = extract_doc_metadata(headline)
    assert doc_type == "Nghị quyết"
    assert doc_number == "33/NQ-CP"
    assert issuing_body == "Chính phủ"


def test_extract_doc_metadata_chi_thi_thu_tuong():
    headline = "Thủ tướng Chính phủ ban hành Chỉ thị số 15/CT-TTg về đẩy mạnh giải ngân vốn đầu tư công"
    doc_type, doc_number, issuing_body = extract_doc_metadata(headline)
    assert doc_type == "Chỉ thị"
    assert doc_number == "15/CT-TTG"
    assert issuing_body == "Thủ tướng Chính phủ"


def test_extract_doc_metadata_thong_tu_nhnn():
    headline = "Thông tư số 02/2023/TT-NHNN quy định về việc tổ chức tín dụng cơ cấu lại thời hạn trả nợ"
    doc_type, doc_number, issuing_body = extract_doc_metadata(headline)
    assert doc_type == "Thông tư"
    assert doc_number == "02/2023/TT-NHNN"
    assert issuing_body == "Ngân hàng Nhà nước Việt Nam"


def test_extract_doc_metadata_press_conference():
    headline = "Họp báo Chính phủ thường kỳ tháng 8: Kinh tế vĩ mô ổn định, các cân đối lớn được bảo đảm"
    doc_type, doc_number, issuing_body = extract_doc_metadata(headline)
    assert doc_type == "Thông cáo báo chí"
    assert doc_number is None
    assert issuing_body == "Chính phủ"


def test_parse_article_links_extracts_and_cleans():
    html = """
    <div>
        <a href="/kinh-te/bai-viet-1-102260903.htm">Bài viết kinh tế vĩ mô quan trọng đầu tư</a>
        <a href="/video-phong-su-102.htm">Bỏ qua liên kết video ngắn</a>
        <a href="/media-anh/anh-dep.htm">Bỏ qua liên kết media hình ảnh</a>
        <a href="/chi-dao-dieu-hanh/quyet-dinh-123.htm">Thủ tướng ban hành quyết định quan trọng</a>
        <a href="/ngan-hang/ngan-hang.htm">Ngắn</a>
    </div>
    """
    links = parse_article_links(html)
    assert len(links) == 2
    assert links[0]["url"] == "https://baochinhphu.vn/kinh-te/bai-viet-1-102260903.htm"
    assert links[0]["title"] == "Bài viết kinh tế vĩ mô quan trọng đầu tư"
    assert links[1]["url"] == "https://baochinhphu.vn/chi-dao-dieu-hanh/quyet-dinh-123.htm"


def test_parse_article_record_extracts_all_fields():
    html = """
    <html>
    <head>
        <meta property="og:title" content="Họp báo Chính phủ thường kỳ" />
        <meta property="article:published_time" content="2026-09-03T16:26:00+07:00" />
    </head>
    <body>
        <h1>Họp báo Chính phủ thường kỳ tháng 8/2026</h1>
        <h2 class="sapo">Tóm tắt kết luận phiên họp Chính phủ thường kỳ.</h2>
        <div class="detail-content">
            <p>Bộ trưởng, Chủ nhiệm Văn phòng Chính phủ chủ trì họp báo thông tin kết quả.</p>
            <p>Tình hình kinh tế - xã hội tháng 8 tiếp tục xu hướng tích cực, kinh tế vĩ mô ổn định.</p>
            <p>Các cân đối lớn của nền kinh tế được bảo đảm, lạm phát được kiểm soát.</p>
        </div>
    </body>
    </html>
    """
    rec = parse_article_record(html, "https://baochinhphu.vn/hop-bao-chinh-phu.htm")
    assert rec is not None
    assert rec["source"] == "baochinhphu"
    assert rec["issuing_body"] == "Chính phủ"
    assert rec["doc_type"] == "Thông cáo báo chí"
    assert "Họp báo Chính phủ thường kỳ" in rec["headline"]
    assert rec["published_at"].year == 2026
    assert rec["summary"] == "Tóm tắt kết luận phiên họp Chính phủ thường kỳ."
    assert len(rec["body"]) > 100


def test_write_macro_policy_is_idempotent():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA staging; CREATE SCHEMA core;")
    con.execute("""
        CREATE TABLE staging.macro_policy (
            source VARCHAR, issuing_body VARCHAR, doc_type VARCHAR, doc_number VARCHAR,
            published_at TIMESTAMP, available_at TIMESTAMP, headline VARCHAR, summary VARCHAR,
            body VARCHAR, source_url VARCHAR, fetched_at TIMESTAMP
        );
        CREATE TABLE core.macro_policy (
            source VARCHAR, issuing_body VARCHAR, doc_type VARCHAR, doc_number VARCHAR,
            published_at TIMESTAMP, available_at TIMESTAMP, headline VARCHAR, summary VARCHAR,
            body VARCHAR, source_url VARCHAR PRIMARY KEY, fetched_at TIMESTAMP
        );
    """)

    now = dt.datetime.now(dt.timezone.utc)
    df = pd.DataFrame([{
        "source": "baochinhphu",
        "issuing_body": "Chính phủ",
        "doc_type": "Nghị quyết",
        "doc_number": "33/NQ-CP",
        "published_at": now,
        "available_at": now,
        "headline": "Nghị quyết số 33/NQ-CP về thị trường BĐS",
        "summary": "Tóm tắt nghị quyết",
        "body": "Nội dung đầy đủ của nghị quyết số 33/NQ-CP tháo gỡ khó khăn cho thị trường BĐS...",
        "source_url": "https://baochinhphu.vn/nghi-quyet-33.htm",
        "fetched_at": now,
    }])

    # First write
    n1 = write_macro_policy(con, df)
    assert n1 == 1
    assert con.execute("SELECT COUNT(*) FROM core.macro_policy").fetchone()[0] == 1

    # Second write (duplicate source_url)
    write_macro_policy(con, df)
    # Core count remains 1 due to ON CONFLICT DO NOTHING
    assert con.execute("SELECT COUNT(*) FROM core.macro_policy").fetchone()[0] == 1


def test_write_macro_policy_rejects_schema_mismatch():
    con = duckdb.connect(":memory:")
    bad_df = pd.DataFrame([{"wrong_col": 123}])
    with pytest.raises(ValueError, match="Missing required column"):
        write_macro_policy(con, bad_df)
