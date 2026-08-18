"""F009 item 5 verification."""
from __future__ import annotations

import datetime as dt
import sys
import pathlib

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from etl import migrations  # noqa: E402
from etl import news_dedup  # noqa: E402


def _news_rows() -> pd.DataFrame:
    base = dt.datetime(2026, 8, 1, 9, 0, 0)
    return pd.DataFrame(
        {
            "symbol": ["FPT", "FPT", "FPT", "FPT"],
            "published_at": [base, base + dt.timedelta(hours=1), base + dt.timedelta(hours=20), base],
            "headline": [
                "FPT sắp phát hành hơn 171 triệu cổ phiếu thưởng cho cổ đông",
                "FPT sap phat hanh hon 171 trieu co phieu thuong cho co dong",  # same event, diacritics-stripped
                "FPT thông báo chi trả cổ tức quý 3",  # unrelated, far in time too
                "Completely unrelated headline about something else entirely",  # same time, not similar
            ],
            "source_url": [
                "https://vnstock.example/a1",
                "https://cafef.example/a2",
                "https://vnstock.example/a3",
                "https://cafef.example/a4",
            ],
        }
    )


def test_find_near_duplicates_flags_similar_headlines_within_window():
    out = news_dedup.find_near_duplicates(_news_rows())
    # a2 should be flagged as a duplicate of a1 (similar headline, 1hr apart)
    row = out[out["source_url"] == "https://cafef.example/a2"]
    assert not row.empty
    assert row.iloc[0]["duplicate_of"] == "https://vnstock.example/a1"


def test_find_near_duplicates_does_not_flag_dissimilar_headlines_same_time():
    out = news_dedup.find_near_duplicates(_news_rows())
    assert "https://cafef.example/a4" not in out["source_url"].tolist()


def test_find_near_duplicates_does_not_flag_similar_headlines_outside_window():
    # a3 is 20 hours after a1 -- outside the 6-hour DUPLICATE_TIME_WINDOW,
    # even though it's also unrelated content, confirms the window cutoff
    # itself is respected (not just similarity).
    out = news_dedup.find_near_duplicates(_news_rows())
    assert "https://vnstock.example/a3" not in out["source_url"].tolist()


def test_find_near_duplicates_empty_input():
    out = news_dedup.find_near_duplicates(pd.DataFrame(columns=["symbol", "published_at", "headline", "source_url"]))
    assert out.empty


def test_apply_duplicate_flags_writes_and_never_overwrites_existing(tmp_path):
    db_path = tmp_path / "test.duckdb"
    con = db.bootstrap_schema(db_path)
    migrations.migrate_news_add_duplicate_of_column(con)

    con.execute(
        "INSERT INTO core.news VALUES "
        "('FPT','vnstock','2026-08-01 09:00:00','2026-08-01 09:00:00','H1',NULL,'u1','2026-08-01 09:00:00',NULL), "
        "('FPT','cafef','2026-08-01 10:00:00','2026-08-01 10:00:00','H2',NULL,'u2','2026-08-01 10:00:00',NULL)"
    )

    mapping = pd.DataFrame([{"source_url": "u2", "duplicate_of": "u1"}])
    n = news_dedup.apply_duplicate_flags(mapping, con)
    assert n == 1

    result = con.execute("SELECT source_url, duplicate_of FROM core.news ORDER BY source_url").fetchall()
    assert result == [("u1", None), ("u2", "u1")]

    # Re-applying a DIFFERENT mapping for the same row must NOT overwrite
    # the existing flag (manual-correction-safe).
    other_mapping = pd.DataFrame([{"source_url": "u2", "duplicate_of": "some_other_url"}])
    news_dedup.apply_duplicate_flags(other_mapping, con)
    result2 = con.execute("SELECT duplicate_of FROM core.news WHERE source_url = 'u2'").fetchone()
    assert result2[0] == "u1"  # unchanged