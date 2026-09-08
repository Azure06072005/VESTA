
"""F102 -> F201 real integration check (scratch, not a permanent test).

Purpose: every existing test exercises pit_join.py and
backtest_meanreversion.py SEPARATELY, each against its own hand-built
fixture. Neither test suite proves the two modules' real outputs/inputs
actually line up end-to-end -- e.g. that core.pit_events' real column
names/types coming out of pit_join.write_events() are exactly what
backtest_meanreversion.load_events()'s SQL query expects.

This script bootstraps a real (temporary) DuckDB, seeds synthetic
OHLCV+news through the same helpers tests/test_pit_join.py uses, runs the
REAL pit_join.build_events_for_symbol() + write_events() production code
path, then feeds the REAL resulting core.pit_events table straight into
backtest_meanreversion.load_events() + run_backtest() -- proving the full
F102->F201 chain works end-to-end with actual DuckDB I/O in the loop, not
just two isolated unit-test fixtures.

This is NOT a claim of a real statistical result (data is synthetic) --
it is an integration/plumbing check only.
"""
from __future__ import annotations

import datetime as dt
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import duckdb  # noqa: E402

from etl import db, migrations  # noqa: E402
from pipeline import pit_join, backtest_meanreversion as bmr  # noqa: E402


def seed_ohlcv(con: duckdb.DuckDBPyConnection, symbol: str, n_days: int = 60) -> None:
    base_date = dt.date(2024, 1, 2)
    price = 100.0
    for i in range(n_days):
        d = base_date + dt.timedelta(days=i)
        if d.weekday() >= 5:  # skip weekends, real trading calendars do too
            continue
        price += 0.1  # mild upward drift so t30 tends to differ from t5
        con.execute(
            "INSERT INTO core.market_ohlcv_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [symbol, d.isoformat(), price, price, price, price, 1_000_000, dt.datetime(2024, 1, 1)],
        )


def seed_news(con: duckdb.DuckDBPyConnection, symbol: str) -> None:
    headlines = [
        ("https://example.com/1", "2024-01-05T10:00:00", "Cong ty bao lo rong trong quy nay"),  # negative
        ("https://example.com/2", "2024-01-10T09:00:00", "FPT bao lai rong tang manh"),  # positive
        ("https://example.com/3", "2024-01-15T16:30:00", "Doanh nghiep to chuc hoi thao"),  # neutral, after close
    ]
    for url, published_at, headline in headlines:
        con.execute(
            "INSERT INTO core.news VALUES (?, 'vnstock', ?, ?, ?, NULL, ?, ?, NULL)",
            [symbol, published_at, published_at, headline, url, dt.datetime(2024, 1, 1)],
        )


def main() -> None:
    db_path = pathlib.Path(tempfile.gettempdir()) / "f201_integration_check.duckdb"
    if db_path.exists():
        db_path.unlink()

    con = db.bootstrap_schema(db_path)
    migrations.migrate_news_add_duplicate_of_column(con)

    symbol = "FPT"
    seed_ohlcv(con, symbol)
    seed_news(con, symbol)

    print("=== Running REAL pit_join.build_events_for_symbol() ===")
    events_df = pit_join.build_events_for_symbol(con, symbol)
    print(f"build_events_for_symbol returned {len(events_df)} rows")
    print(events_df[["symbol", "published_at", "headline", "price_at_publish", "price_t5", "price_t30"]])

    print("\n=== Running REAL pit_join.write_events() ===")
    n_written = pit_join.write_events(events_df, con=con)
    print(f"write_events wrote {n_written} rows to core.pit_events")

    print("\n=== Running REAL backtest_meanreversion.load_events() against the actual core.pit_events table ===")
    loaded_df = bmr.load_events(con)
    print(f"load_events returned {len(loaded_df)} rows")
    print(loaded_df[["symbol", "headline", "price_at_publish", "price_t5", "price_t30"]])

    print("\n=== Running REAL backtest_meanreversion.run_backtest() on the real-schema output ===")
    report = bmr.run_backtest(loaded_df)
    print(f"total_events_loaded={report['total_events_loaded']}")
    print(f"sentiment_class_counts={report['sentiment_class_counts']}")
    print(f"negative_sentiment_group={report['overall']['negative_sentiment_group']}")

    con.close()
    db_path.unlink()
    print("\n=== INTEGRATION CHECK PASSED: F102 -> F201 schema/plumbing confirmed compatible end-to-end ===")


if __name__ == "__main__":
    main()