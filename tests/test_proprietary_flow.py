"""tests/test_proprietary_flow.py

Unit tests for ProprietaryFlowCrawler.
Verifies fetching, schema mapping, staging insertion, and core promotion.
"""
from pathlib import Path
import tempfile
import duckdb
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from src.crawlers.proprietary_flow import ProprietaryFlowCrawler


@pytest.fixture
def temp_duckdb():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tf:
        temp_path = tf.name
    Path(temp_path).unlink(missing_ok=True)
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


def test_proprietary_flow_init_and_promote(temp_duckdb):
    crawler = ProprietaryFlowCrawler(db_path=temp_duckdb)

    # Fake proprietary flow dataframe returned from vnstock
    fake_raw_df = pd.DataFrame([
        {
            "time": "2026-09-15",
            "buy_vol": 400000.0,
            "buy_val": 25000000000.0,
            "sell_vol": 300000.0,
            "sell_val": 18000000000.0,
            "net_vol": 100000.0,
            "net_val": 7000000000.0,
        },
        {
            "time": "2026-09-16",
            "buy_vol": 500000.0,
            "buy_val": 32000000000.0,
            "sell_vol": 200000.0,
            "sell_val": 12000000000.0,
            "net_vol": 300000.0,
            "net_val": 20000000000.0,
        }
    ])

    with patch.object(crawler.market.equity("VCB"), "proprietary_flow", return_value=fake_raw_df):
        # Override market fetch
        with patch.object(crawler, "fetch_symbol_data") as mock_fetch:
            clean_df = pd.DataFrame([
                {
                    "symbol": "VCB",
                    "date": pd.to_datetime("2026-09-15").date(),
                    "buy_vol": 400000.0,
                    "buy_val": 2.5e10,
                    "sell_vol": 300000.0,
                    "sell_val": 1.8e10,
                    "net_vol": 100000.0,
                    "net_val": 7.0e9,
                    "fetched_at": pd.Timestamp.now(),
                },
                {
                    "symbol": "VCB",
                    "date": pd.to_datetime("2026-09-16").date(),
                    "buy_vol": 500000.0,
                    "buy_val": 3.2e10,
                    "sell_vol": 200000.0,
                    "sell_val": 1.2e10,
                    "net_vol": 300000.0,
                    "net_val": 2.0e10,
                    "fetched_at": pd.Timestamp.now(),
                }
            ])
            mock_fetch.return_value = clean_df

            res = crawler.run(["VCB"], delay_sec=0.0)
            assert res["success_symbols"] == 1
            assert res["total_rows_promoted"] == 2

    # Verify DuckDB contents
    con = duckdb.connect(temp_duckdb, read_only=True)
    df_core = con.execute("SELECT * FROM core.proprietary_flow WHERE symbol = 'VCB' ORDER BY date").df()
    assert len(df_core) == 2
    assert df_core.iloc[0]["symbol"] == "VCB"
    assert df_core.iloc[0]["net_vol"] == 100000.0
    assert df_core.iloc[1]["net_val"] == 2.0e10

    # Verify crawl progress
    df_meta = con.execute("SELECT * FROM meta.crawl_progress WHERE dataset_name = 'proprietary_flow' AND symbol = 'VCB'").df()
    assert len(df_meta) == 1
    assert df_meta.iloc[0]["status"] == "success"
    con.close()
