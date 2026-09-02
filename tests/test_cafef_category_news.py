from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.cafef_category_news import (
    CATEGORY_IDS,
    fetch_timeline_page,
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


def test_unconfirmed_category_raises_loudly():
    with pytest.raises(ValueError, match="No confirmed category_id"):
        fetch_timeline_page("some-unconfirmed-category", page=2)


def test_confirmed_categories_only_contains_verified_entry():
    # Deliberately narrow -- only extend after capturing a real .har for a
    # new category, never by guessing an id pattern.
    assert CATEGORY_IDS == {"tai-chinh-quoc-te": 18832}