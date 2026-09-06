from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.cafef_category_orchestrator import (
    extract_symbol,
    enrich_article_record,
    write_category_news,
)


@pytest.fixture
def valid_symbols() -> set[str]:
    return {"VIC", "VHM", "FPT", "HPG", "VNM", "TCB", "SSI", "KBC", "AMD", "AAS"}


def test_extract_symbol_from_url_slug(valid_symbols):
    title = "Doanh thu quý 2 tăng trưởng đột biến"
    url = "https://cafef.vn/FPT-2964370/fpt-doanh-thu-quy-2.chn"
    assert extract_symbol(title, url, valid_symbols) == "FPT"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Cổ phiếu HPG bứt phá mạnh mẽ phiên hôm nay", "HPG"),
        ("Doanh nghiệp liên quan muốn gom 10 triệu cổ phiếu KBC", "KBC"),
        ("Khối ngoại gom mạnh mã chứng khoán FPT trong phiên ATC", "FPT"),
        ("Chứng khoán SSI (mã CK: SSI) thông qua kế hoạch tăng vốn", "SSI"),
        ("Chứng khoán Smart Invest (mã: AAS) báo lãi lớn quý 3", "AAS"),
    ],
)
def test_extract_symbol_positive_syntactic_matches(title, expected, valid_symbols):
    url = "https://cafef.vn/doanh-nghiep-12345.chn"
    assert extract_symbol(title, url, valid_symbols) == expected


@pytest.mark.parametrize(
    "headline",
    [
        # Bare acronym false-positive collisions
        "Thông tin lương thưởng của chủ tịch, CEO Vingroup",
        "15 năm dưới thời CEO Tim Cook: Cổ phiếu Apple tăng 2.300%",
        "TP.HCM làm Quảng trường, Trung tâm hành chính tại Thủ Thiêm gần 29.600 tỷ đồng",
        "Cận cảnh đường xuyên rừng ngập mặn TP.HCM được đề xuất mở rộng lên 10 làn xe",
        "Giá vàng SJC tiếp tục đi ngang, vàng nhẫn tại nhiều thương hiệu đồng loạt hạ nhiệt",
        "Giá vàng được dự báo có thể sớm đạt 5.400 USD/ounce",
        "Ông Peskov hé lộ về chuyến thăm Nga của giám đốc CIA Ratcliffe",
        "Nhiều doanh nghiệp SME có thời gian hoạt động dài trên 5 năm",
        "Suzuki trình làng ADX125 Plus giá 44 triệu nhờ phanh ABS hệ thống TCS",
        "TST: Bão lửa! 72 tàu bị tấn công, Kiev hứng đòn chưa từng có",
        "CNN: Động thái bất ngờ của giới chức Mỹ",
        "Dàn shipper VIP mặc vest đen đi giao điện thoại",
        "Thị trường tài chính quốc tế phản ứng trước quyết định của Fed",
        # Non-stock uses of 'mã'
        "Nhập mã QR để nhận ưu đãi thanh toán",
        "Tặng mã giảm giá 50% cho khách hàng",
        "Mã số thuế doanh nghiệp 0101234567",
        "Mã vùng điện thoại TP.HCM vừa thay đổi",
        "Cảnh báo mã độc nguy hiểm tấn công smartphone",
        "Nhập mã OTP để xác thực giao dịch",
        # Lowercase candidate (regex case-sensitivity safety)
        "cổ phiếu abc tăng trần phiên hôm nay",
        # Dropped bare title prefix
        "VIC: CBTT ban hành Nghị quyết HĐQT số 29",
    ],
)
def test_extract_symbol_negative_cases_return_none(headline, valid_symbols):
    url = "https://cafef.vn/thi-truong-12345.chn"
    assert extract_symbol(headline, url, valid_symbols) is None


def test_extract_symbol_category_tai_chinh_quoc_te_returns_none(valid_symbols):
    title = "Cổ phiếu VIC tăng mạnh trong phiên giao dịch"
    url = "https://cafef.vn/art-123.chn"
    # International category is excluded by design
    assert extract_symbol(title, url, valid_symbols, category_slug="tai-chinh-quoc-te") is None


def test_extract_symbol_foreign_ticker_collision_handling(valid_symbols):
    url = "https://cafef.vn/art-123.chn"
    # Foreign AMD chipmaker context (no domestic context) fails closed
    title_foreign = "Cổ phiếu AMD bùng nổ nhờ làn sóng chip AI toàn cầu"
    assert extract_symbol(title_foreign, url, valid_symbols) is None

    # Domestic FLC Stone AMD context with domestic corroboration succeeds
    title_domestic = "FLC Stone: Cổ phiếu AMD tiếp tục bị duy trì diện đình chỉ giao dịch"
    assert extract_symbol(title_domestic, url, valid_symbols) == "AMD"


def test_enrich_article_record_extracts_when_symbol_matched(monkeypatch, valid_symbols):
    mock_html = (
        '<html><head><meta property="article:published_time" content="2026-09-02T10:00:00" /></head>'
        '<body><div class="detail-content"><p>Paragraph 1.</p><p>Paragraph 2.</p></div></body></html>'
    )
    monkeypatch.setattr("crawlers.cafef_category_orchestrator.fetch_article_html", lambda url: mock_html)

    article_link = {
        "title": "Cổ phiếu FPT: Lợi nhuận tăng trưởng mạnh",
        "url": "https://cafef.vn/fpt-loi-nhuan-123.chn",
    }
    rec = enrich_article_record(article_link, valid_symbols)
    assert rec is not None
    assert rec["symbol"] == "FPT"
    assert rec["source"] == "cafef"
    assert rec["headline"] == "Cổ phiếu FPT: Lợi nhuận tăng trưởng mạnh"
    assert rec["body"] == "Paragraph 1.\n\nParagraph 2."
    assert rec["source_url"] == "https://cafef.vn/fpt-loi-nhuan-123.chn"
    assert isinstance(rec["published_at"], dt.datetime)
    assert rec["published_at"].isoformat().startswith("2026-09-02")


def test_enrich_article_record_returns_none_when_no_symbol(monkeypatch, valid_symbols):
    article_link = {
        "title": "Thị trường tài chính quốc tế phản ứng trước quyết định của Fed",
        "url": "https://cafef.vn/fed-123.chn",
    }
    # Should fail closed and return None without fetching HTML
    rec = enrich_article_record(article_link, valid_symbols)
    assert rec is None


def test_write_category_news_is_idempotent():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA core")
    con.execute("""
    CREATE TABLE core.news (
        symbol       VARCHAR NOT NULL,
        source       VARCHAR NOT NULL,
        published_at TIMESTAMP NOT NULL,
        available_at TIMESTAMP NOT NULL,
        headline     VARCHAR NOT NULL,
        body         VARCHAR,
        source_url   VARCHAR NOT NULL,
        fetched_at   TIMESTAMP NOT NULL,
        PRIMARY KEY (source_url)
    )
    """)

    df = pd.DataFrame([
        {
            "symbol": "FPT",
            "source": "cafef",
            "published_at": dt.datetime(2026, 9, 2, 10, 0, tzinfo=dt.timezone.utc),
            "available_at": dt.datetime(2026, 9, 2, 10, 0, tzinfo=dt.timezone.utc),
            "headline": "Cổ phiếu FPT tăng trưởng",
            "body": "Body text of FPT article",
            "source_url": "https://cafef.vn/fpt-1.chn",
            "fetched_at": dt.datetime.now(dt.timezone.utc),
        },
        {
            "symbol": "HPG",
            "source": "cafef",
            "published_at": dt.datetime(2026, 9, 2, 11, 0, tzinfo=dt.timezone.utc),
            "available_at": dt.datetime(2026, 9, 2, 11, 0, tzinfo=dt.timezone.utc),
            "headline": "Cổ phiếu HPG bứt phá",
            "body": "Body text of HPG article",
            "source_url": "https://cafef.vn/hpg-1.chn",
            "fetched_at": dt.datetime.now(dt.timezone.utc),
        }
    ])

    # First write
    n1 = write_category_news(con, df)
    assert n1 == 2
    count1 = con.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
    assert count1 == 2

    # Second write with same URLs (idempotency)
    n2 = write_category_news(con, df)
    assert n2 == 0
    count2 = con.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
    assert count2 == 2

    con.close()
