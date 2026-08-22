"""F102 verification.

Per the feature spec: 'explicit look-ahead-bias unit test, this is the
single most important test in the repo.' The two tests that matter most:
a news item published after market close is NOT joined to that same
day's close, and a fundamental row is NOT visible before its available_at
(here: before get_as_of's fetched_at/available_at gate lets it through).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402

from etl import db  # noqa: E402
from etl import migrations  # noqa: E402
from crawlers import fundamentals  # noqa: E402
from pipeline import pit_join  # noqa: E402


def _setup_db(tmp_path) -> "duckdb.DuckDBPyConnection":
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    migrations.migrate_news_add_duplicate_of_column(con)  # duplicate_of is migration-added, not base schema
    return con


def _seed_ohlcv(con, symbol: str, dates: list[str], closes: list[float]) -> None:
    for d, c in zip(dates, closes):
        con.execute(
            "INSERT INTO core.market_ohlcv_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [symbol, d, c, c, c, c, 1000, dt.datetime(2026, 1, 1)],
        )


def _seed_news(con, symbol: str, source_url: str, published_at: str, headline: str = "H") -> None:
    con.execute(
        "INSERT INTO core.news VALUES (?, 'vnstock', ?, ?, ?, NULL, ?, ?, NULL)",
        [symbol, published_at, published_at, headline, source_url, dt.datetime(2026, 1, 1)],
    )


def test_get_trading_calendar_returns_only_crawled_dates(tmp_path):
    con = _setup_db(tmp_path)
    _seed_ohlcv(con, "FPT", ["2026-01-02", "2026-01-05", "2026-01-06"], [100, 101, 102])
    # 2026-01-03/04 deliberately absent (weekend) -- confirms the calendar
    # is derived from real crawled data, not a generated date range.
    calendar = pit_join.get_trading_calendar(con, "FPT")
    assert calendar == [dt.date(2026, 1, 2), dt.date(2026, 1, 5), dt.date(2026, 1, 6)]


def test_effective_trading_date_before_market_close_uses_same_day():
    trading_days = [dt.date(2026, 1, 2), dt.date(2026, 1, 5)]
    published = dt.datetime(2026, 1, 2, 10, 0)  # 10:00, before 15:00 close
    assert pit_join.effective_trading_date(published, trading_days) == dt.date(2026, 1, 2)


def test_effective_trading_date_after_market_close_uses_next_trading_day():
    # THE core look-ahead-bias test the spec calls out explicitly: a news
    # item published after market close must NOT be joined to that same
    # day's close.
    trading_days = [dt.date(2026, 1, 2), dt.date(2026, 1, 5)]
    published = dt.datetime(2026, 1, 2, 16, 0)  # 16:00, after 15:00 close
    assert pit_join.effective_trading_date(published, trading_days) == dt.date(2026, 1, 5)


def test_effective_trading_date_on_non_trading_day_uses_next_trading_day():
    trading_days = [dt.date(2026, 1, 2), dt.date(2026, 1, 5)]
    published = dt.datetime(2026, 1, 3, 10, 0)  # Saturday, no trading
    assert pit_join.effective_trading_date(published, trading_days) == dt.date(2026, 1, 5)


def test_effective_trading_date_returns_none_when_no_future_trading_day_exists():
    trading_days = [dt.date(2026, 1, 2)]
    published = dt.datetime(2026, 1, 5, 10, 0)  # after the only crawled date
    assert pit_join.effective_trading_date(published, trading_days) is None


def test_price_at_horizon_returns_none_when_insufficient_future_data():
    trading_days = [dt.date(2026, 1, 2), dt.date(2026, 1, 5)]
    price_by_date = {dt.date(2026, 1, 2): 100.0, dt.date(2026, 1, 5): 101.0}
    # t+5 doesn't exist yet -- must be None, never fabricated/extrapolated.
    result = pit_join.price_at_horizon(trading_days, price_by_date, dt.date(2026, 1, 2), 5)
    assert result is None


def test_price_at_horizon_returns_real_value_when_available():
    trading_days = [dt.date(2026, 1, 2), dt.date(2026, 1, 5)]
    price_by_date = {dt.date(2026, 1, 2): 100.0, dt.date(2026, 1, 5): 101.0}
    result = pit_join.price_at_horizon(trading_days, price_by_date, dt.date(2026, 1, 2), 1)
    assert result == 101.0


def test_build_events_excludes_duplicate_flagged_news(tmp_path):
    con = _setup_db(tmp_path)
    _seed_ohlcv(con, "FPT", ["2026-01-02"], [100.0])
    _seed_news(con, "FPT", "u1", "2026-01-02 10:00:00")
    _seed_news(con, "FPT", "u2", "2026-01-02 10:05:00")
    con.execute("UPDATE core.news SET duplicate_of = 'u1' WHERE source_url = 'u2'")

    events = pit_join.build_events_for_symbol(con, "FPT")
    assert len(events) == 1  # u2 excluded as a flagged duplicate
    assert events.iloc[0]["source_url"] == "u1"


def test_build_events_joins_adjusted_price_not_raw_close(tmp_path):
    con = _setup_db(tmp_path)
    _seed_ohlcv(con, "FPT", ["2026-01-02", "2026-01-05"], [100.0, 100.0])
    con.execute(
        "INSERT INTO core.price_adjustment_events VALUES "
        "('FPT', '2026-01-05', 'share_issue', 0.5, 'EVT1', '2026-01-01 00:00:00')"
    )
    _seed_news(con, "FPT", "u1", "2026-01-02 10:00:00")

    events = pit_join.build_events_for_symbol(con, "FPT")
    row = events.iloc[0]
    # 2026-01-02 is BEFORE the 2026-01-05 ex_date, so the 0.5 multiplier
    # applies -- adjusted price should be 50.0, not the raw 100.0.
    assert row["price_at_publish"] == 50.0


def test_build_events_uses_get_as_of_not_a_future_revision(tmp_path):
    # THE other core look-ahead-bias test: a fundamental revision that
    # wasn't yet observed as of published_at must not leak in.
    con = _setup_db(tmp_path)
    _seed_ohlcv(con, "FPT", ["2026-01-02"], [100.0])

    # period_end 2025-09-30 -> available_at = 2025-09-30 + 30 days = 2025-10-30,
    # well before published_at (2026-01-02) so the ORIGINAL value can
    # legitimately be "available" as of the news date.
    original = fundamentals.melt_pivoted_statement(
        pd.DataFrame({"item_id": ["revenue"], "2025-Q3": [100.0]}), "FPT", "income_statement"
    )
    fundamentals.write_statements(original, con)
    # Force the original row's fetched_at to genuinely precede published_at.
    con.execute(
        "UPDATE core.fundamentals SET fetched_at = ? WHERE symbol = 'FPT' AND data_json LIKE '%100.0%'",
        [dt.datetime(2025, 11, 1)],
    )

    _seed_news(con, "FPT", "u1", "2026-01-02 10:00:00")

    # A restatement fetched well AFTER published_at -- its fetched_at is
    # left as real "now" (test execution time), which is already after
    # 2026-01-02 in any real run, so no manipulation needed here.
    restated = fundamentals.melt_pivoted_statement(
        pd.DataFrame({"item_id": ["revenue"], "2025-Q3": [999.0]}), "FPT", "income_statement"
    )
    fundamentals.write_statements(restated, con)

    events = pit_join.build_events_for_symbol(con, "FPT")
    row = events.iloc[0]
    metrics = json.loads(row["fundamentals_json"])["income_statement"]
    assert metrics["revenue"] == 100.0  # the ORIGINAL value, not 999.0 -- no look-ahead


def test_build_events_returns_empty_when_no_news(tmp_path):
    con = _setup_db(tmp_path)
    _seed_ohlcv(con, "FPT", ["2026-01-02"], [100.0])
    events = pit_join.build_events_for_symbol(con, "FPT")
    assert events.empty


def test_write_events_is_idempotent_and_rebuilds_on_rerun(tmp_path):
    con = _setup_db(tmp_path)
    _seed_ohlcv(con, "FPT", ["2026-01-02"], [100.0])
    _seed_news(con, "FPT", "u1", "2026-01-02 10:00:00")

    events = pit_join.build_events_for_symbol(con, "FPT")
    n1 = pit_join.write_events(events, con)
    n2 = pit_join.write_events(events, con)  # re-run, same input
    assert n1 == n2 == 1

    row_count = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE symbol = 'FPT'").fetchone()[0]
    assert row_count == 1  # not doubled


def test_write_events_rejects_schema_mismatch(tmp_path):
    con = _setup_db(tmp_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})

    with pytest.raises(ValueError, match="missing columns"):
        pit_join.write_events(bad_df, con)