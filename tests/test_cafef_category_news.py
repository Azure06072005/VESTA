from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.cafef_category_news import (
    CATEGORY_IDS,
    parse_article_links,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def timeline_page2() -> str:
    return (FIXTURES / "real_timeline_page2.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def timeline_page5() -> str:
    return (FIXTURES / "real_timeline_page5.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def category_landing() -> str:
    return (FIXTURES / "real_category_landing.html").read_text(encoding="utf-8")


def test_timeline_page2_returns_15_real_articles(timeline_page2):
    articles = parse_article_links(timeline_page2)
    assert len(articles) == 15


def test_timeline_page5_returns_15_real_articles(timeline_page5):
    articles = parse_article_links(timeline_page5)
    assert len(articles) == 15


def test_timeline_page2_first_article_matches_real_capture(timeline_page2):
    articles = parse_article_links(timeline_page2)
    first = articles[0]
    assert first["title"] == "Điều gì xảy ra khi tàu sân bay Mỹ 82.000 tấn đâm tuần dương hạm?"
    assert first["url"] == (
        "https://cafef.vn/dieu-gi-xay-ra-khi-tau-san-bay-my-82000-tan-dam-tuan-duong-ham-"
        "188260902074118446.chn"
    )


def test_category_landing_page_uses_different_classes_but_same_rule(category_landing):
    """The landing page mixes 4 different wrapper classes (firstitem/big/
    item, confirmed live) -- this must still work via the shared
    div[role='article'] -> h3 a rule, not a class-specific selector.
    """
    articles = parse_article_links(category_landing)
    assert len(articles) == 37


def test_all_urls_are_absolute():
    html = '<div role="article"><h3><a href="/some-article-123.chn">Title</a></h3></div>'
    articles = parse_article_links(html)
    assert articles[0]["url"] == "https://cafef.vn/some-article-123.chn"


def test_no_articles_found_raises_loudly():
    with pytest.raises(ValueError, match="No div\\[role='article'\\]"):
        parse_article_links("<html><body>nothing here</body></html>")


def test_confirmed_categories_contains_all_verified_entries():
    # Confirmed live 2026-09-02 for 9 core financial and market categories
    expected = {
        "thi-truong-chung-khoan": 18831,
        "tai-chinh-quoc-te": 18832,
        "vi-mo-dau-tu": 18833,
        "tai-chinh-ngan-hang": 18834,
        "bat-dong-san": 18835,
        "doanh-nghiep": 18836,
        "thi-truong": 18839,
        "kinh-te-so": 188127,
        "smart-money": 1882020,
    }
    assert CATEGORY_IDS == expected


def test_discover_category_id_from_landing_html(category_landing):
    from crawlers.cafef_category_news import discover_category_id

    # Test discovering from HTML
    cid = discover_category_id("tai-chinh-quoc-te", html=category_landing)
    assert cid == 18832


def test_discover_category_id_invalid_html_raises():
    from crawlers.cafef_category_news import discover_category_id

    with pytest.raises(ValueError, match="Could not discover category_id"):
        discover_category_id("non-existent-cat", html="<html><body>No inputs here</body></html>")