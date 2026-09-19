"""tests/test_macro_rates.py

Unit tests for MacroRatesCrawler.
Verifies parsing of VN10Y bond yields and interbank interest rates.
"""
from pathlib import Path
import tempfile
import duckdb
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from src.crawlers.macro_rates import MacroRatesCrawler


@pytest.fixture
def temp_duckdb():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tf:
        temp_path = tf.name
    Path(temp_path).unlink(missing_ok=True)
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


def test_macro_rates_init_and_promote(temp_duckdb):
    crawler = MacroRatesCrawler(db_path=temp_duckdb)

    # Fake VN10Y dataframe
    fake_vn10y_df = pd.DataFrame([
        {
            "rate_type": "GOV_BOND_YIELD",
            "term": "10Y",
            "date": pd.to_datetime("2026-09-17").date(),
            "rate_value": 4.577,
            "source": "investing_vn10y",
            "fetched_at": pd.Timestamp.now(),
        },
        {
            "rate_type": "GOV_BOND_YIELD",
            "term": "10Y",
            "date": pd.to_datetime("2026-09-16").date(),
            "rate_value": 4.577,
            "source": "investing_vn10y",
            "fetched_at": pd.Timestamp.now(),
        }
    ])

    # Fake Interbank dataframe
    fake_ib_df = pd.DataFrame([
        {
            "rate_type": "INTERBANK",
            "term": "ON",
            "date": pd.to_datetime("2026-09-15").date(),
            "rate_value": 5.20,
            "source": "sbv_corpus_fix",
            "fetched_at": pd.Timestamp.now(),
        },
        {
            "rate_type": "INTERBANK",
            "term": "1W",
            "date": pd.to_datetime("2026-09-15").date(),
            "rate_value": 5.30,
            "source": "sbv_corpus_fix",
            "fetched_at": pd.Timestamp.now(),
        }
    ])

    with patch.object(crawler, "fetch_vn10y_investing", return_value=fake_vn10y_df):
        with patch.object(crawler, "backfill_interbank_from_corpus", return_value=fake_ib_df):
            res = crawler.run()
            assert res["vn10y_rows"] == 2
            assert res["interbank_rows"] == 2
            assert res["total_promoted"] == 4

    # Verify DuckDB core.macro_rates
    con = duckdb.connect(temp_duckdb, read_only=True)
    df_core = con.execute("SELECT * FROM core.macro_rates ORDER BY date, term").df()
    assert len(df_core) == 4
    con.close()
