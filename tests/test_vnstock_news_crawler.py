"""F003 verification.

normalize_news/write_news are pure/DB-only and tested here without
network access. fetch_raw() (the live vnstock call) is NOT covered --
this sandbox cannot reach vnstock's API domain. Run
discover_news_schema.py against a real key to confirm the column aliases
in src/crawlers/vnstock_news.py.
"""
from __future__ import annotations

import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402
from crawlers import vnstock_news  # noqa: E402


def _sample_news_df() -> pd.DataFrame:
    # Confirmed live shape 2026-08-13 (real pasted output for FPT) --
    # trimmed to the columns this crawler actually maps.
    return pd.DataFrame(
        {
            "news_title": ["FPT announces Q2 results", "FPT signs new partnership"],
            "public_date": ["2025-07-20T16:13:52", "2025-07-15T10:51:54"],
            "news_full_content": ["Full article text one...", "Full article text two..."],
            "news_source_link": ["https://example.com/a1", "https://example.com/a2"],
        }
    )


def test_normalize_news_maps_columns_and_adds_symbol():
    out = vnstock_news.normalize_news(_sample_news_df(), "FPT")
    assert list(out.columns) == vnstock_news.NEWS_COLUMNS
    assert (out["symbol"] == "FPT").all()
    assert (out["source"] == "vnstock").all()
    assert len(out) == 2


def test_normalize_news_sets_available_at_equal_to_published_at():
    out = vnstock_news.normalize_news(_sample_news_df(), "FPT")
    assert (out["available_at"] == out["published_at"]).all()


def test_normalize_news_dedupes_by_source_url_within_fetch(capsys):
    dupe = pd.concat([_sample_news_df().iloc[[0]], _sample_news_df().iloc[[0]]])
    out = vnstock_news.normalize_news(dupe, "FPT")
    assert len(out) == 1
    captured = capsys.readouterr()
    assert "dropped 1 duplicate source_url" in captured.out


def test_normalize_news_raises_clearly_on_missing_headline_column():
    drifted = _sample_news_df().drop(columns=["news_title"])
    with pytest.raises(ValueError, match="Could not find a source column for 'headline'"):
        vnstock_news.normalize_news(drifted, "FPT")


def test_normalize_news_raises_empty_result_error_on_empty_fetch():
    # F008-compatible: must be EmptyResultError, not a plain ValueError,
    # so F008's run_job() records this as genuine emptiness, not a
    # transient failure eligible for pointless retries.
    with pytest.raises(EmptyResultError, match="empty DataFrame"):
        vnstock_news.normalize_news(pd.DataFrame(), "FPT")


def test_write_news_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    normalized = vnstock_news.normalize_news(_sample_news_df(), "FPT")

    n1 = vnstock_news.write_news(normalized, con)
    n2 = vnstock_news.write_news(normalized, con)  # re-run, same input
    assert n1 == n2 == 2

    row_count = con.execute("SELECT COUNT(*) FROM core.news WHERE symbol = 'FPT'").fetchone()[0]
    assert row_count == 2  # not doubled


def test_write_news_rejects_schema_mismatch(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})
    with pytest.raises(ValueError, match="missing columns"):
        vnstock_news.write_news(bad_df, con)


def test_write_news_deduped_across_symbols_by_source_url(tmp_path):
    # Two "symbols" citing the exact same article URL should collapse to
    # one core.news row, since source_url is the PRIMARY KEY (shared
    # F003/F004 schema, DECISIONS.md "Dual news source" entry).
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    fpt_news = vnstock_news.normalize_news(_sample_news_df(), "FPT")
    vnstock_news.write_news(fpt_news, con)

    same_url_df = _sample_news_df().iloc[[0]].copy()
    other_symbol_news = vnstock_news.normalize_news(same_url_df, "VNM")
    vnstock_news.write_news(other_symbol_news, con)

    row_count = con.execute(
        "SELECT COUNT(*) FROM core.news WHERE source_url = 'https://example.com/a1'"
    ).fetchone()[0]
    assert row_count == 1