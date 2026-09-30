import pathlib
import sys
import tempfile
import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from crawlers import intraday_ohlcv
from etl import db


def _sample_1m_df(symbol: str = "FPT", count: int = 5) -> pd.DataFrame:
    base_time = pd.Timestamp("2026-09-25 09:15:00")
    records = []
    for i in range(count):
        t = base_time + pd.Timedelta(minutes=i)
        records.append({
            "symbol": symbol,
            "time": t,
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 99.0 + i,
            "close": 101.0 + i,
            "volume": 1000 * (i + 1),
        })
    return pd.DataFrame(records)


def test_validate_1m_bars_drops_corrupted_geometry():
    df = _sample_1m_df("FPT", count=3)
    # Add corrupted rows: low > high, close > high, negative volume
    bad_rows = pd.DataFrame([
        {"symbol": "FPT", "time": pd.Timestamp("2026-09-25 10:00:00"), "open": 100, "high": 90, "low": 95, "close": 92, "volume": 100},  # low > high
        {"symbol": "FPT", "time": pd.Timestamp("2026-09-25 10:01:00"), "open": 100, "high": 105, "low": 95, "close": 110, "volume": 100}, # close > high
        {"symbol": "FPT", "time": pd.Timestamp("2026-09-25 10:02:00"), "open": 100, "high": 105, "low": 95, "close": 100, "volume": -50}, # negative volume
    ])
    combined = pd.concat([df, bad_rows], ignore_index=True)
    validated = intraday_ohlcv.validate_1m_bars(combined)
    assert len(validated) == 3
    assert set(validated["time"]) == set(df["time"])


def test_validate_1m_bars_deduplicates():
    df = _sample_1m_df("FPT", count=3)
    duplicated = pd.concat([df, df], ignore_index=True)
    validated = intraday_ohlcv.validate_1m_bars(duplicated)
    assert len(validated) == 3


def test_write_1m_bars_is_idempotent(tmp_path):
    db_file = tmp_path / "test_intraday.duckdb"
    con = duckdb.connect(str(db_file))
    con.execute("CREATE SCHEMA core;")
    con.execute("""
        CREATE TABLE core.market_ohlcv_1m (
            symbol VARCHAR NOT NULL,
            time TIMESTAMP NOT NULL,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume BIGINT NOT NULL,
            fetched_at TIMESTAMP,
            PRIMARY KEY (symbol, time)
        );
    """)

    df = _sample_1m_df("FPT", count=5)
    inserted1 = intraday_ohlcv.write_1m_bars(df, con)
    assert inserted1 == 5

    # Run again: should insert 0 new rows (idempotent)
    inserted2 = intraday_ohlcv.write_1m_bars(df, con)
    assert inserted2 == 0

    total_rows = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m").fetchone()[0]
    assert total_rows == 5
    con.close()


def test_attach_intraday_cross_database(tmp_path):
    main_db = tmp_path / "main.duckdb"
    intraday_db = tmp_path / "intraday.duckdb"

    # Seed intraday DB
    con_intra = duckdb.connect(str(intraday_db))
    con_intra.execute("CREATE SCHEMA core;")
    con_intra.execute("""
        CREATE TABLE core.market_ohlcv_1m (
            symbol VARCHAR, time TIMESTAMP, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT, fetched_at TIMESTAMP,
            PRIMARY KEY (symbol, time)
        );
    """)
    df = _sample_1m_df("HPG", count=3)
    intraday_ohlcv.write_1m_bars(df, con_intra)
    con_intra.close()

    # Seed main DB
    con_main = duckdb.connect(str(main_db))
    con_main.execute("CREATE SCHEMA core;")
    con_main.execute("CREATE TABLE core.dim_symbol (symbol VARCHAR PRIMARY KEY, exchange VARCHAR);")
    con_main.execute("INSERT INTO core.dim_symbol VALUES ('HPG', 'HOSE');")

    # Attach intraday to main
    db.attach_intraday(con_main, db_path=intraday_db, read_only=True)

    # Perform cross-database join
    joined = con_main.execute("""
        SELECT m.symbol, s.exchange, m.close
        FROM intraday.core.market_ohlcv_1m m
        JOIN core.dim_symbol s ON m.symbol = s.symbol
    """).fetchall()

    assert len(joined) == 3
    assert joined[0][0] == "HPG"
    assert joined[0][1] == "HOSE"
    con_main.close()
