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
    return {"VIC", "VHM", "FPT", "HPG", "VNM", "TCB", "SSI"}


def test_extract_symbol_from_title_prefix(valid_symbols):
    title = "VIC: CBTT ban hành Nghị quyết HĐQT số 29"
    url = "https://cafef.vn/some-article-123.chn"
    assert extract_symbol(title, url, valid_symbols) == "VIC"


def test_extract_symbol_from_url_slug(valid_symbols):
    title = "Doanh thu quý 2 tăng trưởng đột biến"
    url = "https://cafef.vn/FPT-2964370/fpt-doanh-thu-quy-2.chn"
    assert extract_symbol(title, url, valid_symbols) == "FPT"


def test_extract_symbol_from_headline_word(valid_symbols):
    title = "Cổ phiếu HPG bứt phá mạnh mẽ phiên hôm nay"
    url = "https://cafef.vn/co-phieu-but-pha-12345.chn"
    assert extract_symbol(title, url, valid_symbols) == "HPG"


def test_extract_symbol_fallback_to_vnindex(valid_symbols):
    title = "Thị trường tài chính quốc tế phản ứng trước quyết định của Fed"
    url = "https://cafef.vn/thi-truong-phan-ung-12345.chn"
    assert extract_symbol(title, url, valid_symbols) == "VNINDEX"


def test_enrich_article_record_extracts_all_fields(monkeypatch, valid_symbols):
    mock_html = (
        '<html><head><meta property="article:published_time" content="2026-09-02T10:00:00" /></head>'
        '<body><div class="detail-content"><p>Paragraph 1.</p><p>Paragraph 2.</p></div></body></html>'
    )
    monkeypatch.setattr("crawlers.cafef_category_orchestrator.fetch_article_html", lambda url: mock_html)

    article_link = {
        "title": "FPT: Lợi nhuận tăng trưởng mạnh",
        "url": "https://cafef.vn/fpt-loi-nhuan-123.chn",
    }
    rec = enrich_article_record(article_link, valid_symbols)
    assert rec is not None
    assert rec["symbol"] == "FPT"
    assert rec["source"] == "cafef"
    assert rec["headline"] == "FPT: Lợi nhuận tăng trưởng mạnh"
    assert rec["body"] == "Paragraph 1.\n\nParagraph 2."
    assert rec["source_url"] == "https://cafef.vn/fpt-loi-nhuan-123.chn"
    assert isinstance(rec["published_at"], dt.datetime)
    assert rec["published_at"].isoformat().startswith("2026-09-02")


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
            "headline": "FPT Article",
            "body": "Body text of FPT article",
            "source_url": "https://cafef.vn/fpt-1.chn",
            "fetched_at": dt.datetime.now(dt.timezone.utc),
        },
        {
            "symbol": "VNINDEX",
            "source": "cafef",
            "published_at": dt.datetime(2026, 9, 2, 11, 0, tzinfo=dt.timezone.utc),
            "available_at": dt.datetime(2026, 9, 2, 11, 0, tzinfo=dt.timezone.utc),
            "headline": "Macro Article",
            "body": "Body text of macro article",
            "source_url": "https://cafef.vn/macro-1.chn",
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
