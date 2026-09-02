from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.cafef_article_body import parse_article_body

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "real_article_sample.html"
REAL_URL = (
    "https://cafef.vn/khoi-ngoai-ban-rong-hon-90000-ty-tu-dau-nam-nhung-mot-tin-hieu-"
    "tich-cuc-da-xuat-hien-188260901220700323.chn"
)


@pytest.fixture(scope="module")
def real_html() -> str:
    """Real captured HTML from a live .har (2026-09-02), not synthetic --
    this is the actual artifact that unblocked F004b this session.
    """
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_real_article_published_at_extracted(real_html):
    result = parse_article_body(real_html, REAL_URL)
    assert result["published_at"] == "2026-09-02T00:04:00"


def test_real_article_body_is_real_paragraph_count(real_html):
    result = parse_article_body(real_html, REAL_URL)
    # Confirmed live 2026-09-02: 11 <p> paragraphs join to 3,711 chars.
    assert len(result["body"]) == 3711
    assert result["body"].count("\n\n") == 10  # 11 paragraphs -> 10 separators


def test_real_article_body_contains_real_opening_sentence(real_html):
    result = parse_article_body(real_html, REAL_URL)
    assert result["body"].startswith(
        "Từ đầu năm 2026, khối ngoại đã bán ròng trong cả 8 tháng"
    )


def test_missing_container_raises_loudly():
    html_without_container = "<html><body><div class='not-it'>hello</div></body></html>"
    with pytest.raises(ValueError, match="No 'detail-content' container"):
        parse_article_body(html_without_container, "https://cafef.vn/fake.chn")


def test_container_present_but_empty_raises_loudly():
    html_empty_container = '<html><body><div class="detail-content"></div></body></html>'
    with pytest.raises(ValueError, match="no paragraph text"):
        parse_article_body(html_empty_container, "https://cafef.vn/fake.chn")


def test_missing_published_at_meta_does_not_crash():
    html_no_meta = (
        '<html><body><div class="detail-content"><p>Real text here.</p></div>'
        "</body></html>"
    )
    result = parse_article_body(html_no_meta, "https://cafef.vn/fake.chn")
    assert result["published_at"] is None
    assert result["body"] == "Real text here."