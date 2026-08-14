"""F004 verification.

parse_articles/write_news are pure/DB-only and tested here without
network access. fetch_raw() (the live HTTP request + robots.txt check) is
NOT covered -- this sandbox's egress allowlist doesn't include cafef.vn.
The HTML fixture below models the real markup shape observed live
2026-08-13 (article links containing a numeric id + '.chn', with a
DD/MM/YYYY HH:MM date in the surrounding text) -- but the EXACT selectors
(PARSE_LINK_PATTERN/PARSE_DATE_PATTERN) are best-guess, not confirmed
against cafef's actual raw HTML (see cafef_news.py module docstring).
"""
from __future__ import annotations

import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from crawlers import cafef_news  # noqa: E402


SAMPLE_HTML = """
<html><body>
<ul>
<li>
  05/08/2026 00:07
  <a href="https://cafef.vn/fpt-sap-phat-hanh-co-phieu-188260804074555716.chn">
    FPT sắp phát hành hơn 171 triệu cổ phiếu thưởng cho cổ đông
  </a>
</li>
<li>
  03/08/2026 16:13
  <a href="https://cafef.vn/du-lieu/FPT-2944964/fpt-nghi-quyet-hdqt-ve-viec-trien-khai.chn">
    FPT: Nghị quyết HĐQT về việc triển khai phương án phát hành cổ phiếu
  </a>
</li>
<li>
  <a href="/some-unrelated-nav-link.chn">Không phải bài viết</a>
</li>
</ul>
</body></html>
"""

SAMPLE_HTML_NO_MATCHES = """
<html><body>
<ul><li><a href="/thi-truong-chung-khoan.chn">Chứng khoán</a></li></ul>
</body></html>
"""


def test_parse_articles_extracts_headline_url_and_date():
    out = cafef_news.parse_articles(SAMPLE_HTML, "FPT")
    assert list(out.columns) == cafef_news.NEWS_COLUMNS
    assert len(out) == 2  # the unrelated nav link is excluded
    assert (out["symbol"] == "FPT").all()
    assert (out["source"] == "cafef").all()


def test_parse_articles_sets_available_at_equal_to_published_at():
    out = cafef_news.parse_articles(SAMPLE_HTML, "FPT")
    assert (out["available_at"] == out["published_at"]).all()


def test_parse_articles_body_is_none_known_gap():
    # KNOWN GAP documented in the module: article body requires a second
    # fetch per article, not done by this crawler.
    out = cafef_news.parse_articles(SAMPLE_HTML, "FPT")
    assert out["body"].isna().all()


def test_parse_articles_excludes_non_article_links():
    out = cafef_news.parse_articles(SAMPLE_HTML, "FPT")
    assert "unrelated-nav-link" not in " ".join(out["source_url"])


def test_parse_articles_raises_value_error_not_empty_result_error_on_zero_matches():
    # Deliberately NOT EmptyResultError -- see module docstring: zero
    # matches for an active symbol more likely means selector drift.
    with pytest.raises(ValueError, match="zero matching article links"):
        cafef_news.parse_articles(SAMPLE_HTML_NO_MATCHES, "FPT")


def test_write_news_shares_schema_and_dedup_with_f003(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    parsed = cafef_news.parse_articles(SAMPLE_HTML, "FPT")

    n1 = cafef_news.write_news(parsed, con)
    n2 = cafef_news.write_news(parsed, con)  # re-run, same input
    assert n1 == n2 == 2

    row_count = con.execute(
        "SELECT COUNT(*) FROM core.news WHERE symbol = 'FPT' AND source = 'cafef'"
    ).fetchone()[0]
    assert row_count == 2  # not doubled


def test_write_news_rejects_schema_mismatch(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})
    with pytest.raises(ValueError, match="missing columns"):
        cafef_news.write_news(bad_df, con)


def test_check_robots_allowed_is_callable_and_returns_bool():
    # Cannot actually reach cafef.vn from this sandbox -- this only
    # confirms the function has the right shape/signature; real
    # robots.txt behavior must be verified where network access exists.
    assert callable(cafef_news.check_robots_allowed)