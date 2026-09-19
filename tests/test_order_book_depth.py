"""Unit tests for OrderBookDepthCrawler (Order Book Level 2 Depth & Tick Trades)."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.crawlers.order_book_depth import OrderBookDepthCrawler


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test.duckdb")


def test_order_book_schema_init(temp_db):
    crawler = OrderBookDepthCrawler(db_path=temp_db)
    con = crawler.db_path
    import duckdb
    c = duckdb.connect(str(con), read_only=True)
    tables = c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'core'").fetchall()
    table_names = [t[0] for t in tables]
    assert "order_book_depth" in table_names
    assert "intraday_trades" in table_names
    c.close()


def test_order_book_ofi_calculation(temp_db):
    crawler = OrderBookDepthCrawler(db_path=temp_db)

    # Mock order_book dataframe
    mock_ob = pd.DataFrame([{
        "bid_price_1": 21000.0, "bid_vol_1": 10000.0,
        "bid_price_2": 20950.0, "bid_vol_2": 20000.0,
        "bid_price_3": 20900.0, "bid_vol_3": 30000.0,
        "ask_price_1": 21050.0, "ask_vol_1": 5000.0,
        "ask_price_2": 21100.0, "ask_vol_2": 10000.0,
        "ask_price_3": 21150.0, "ask_vol_3": 15000.0,
    }])

    crawler.market.equity = MagicMock()
    crawler.market.equity.return_value.order_book.return_value = mock_ob

    res_df = crawler.fetch_order_book("SSI")
    assert res_df is not None
    assert not res_df.empty
    assert "total_bid_depth" in res_df.columns
    assert "total_ask_depth" in res_df.columns
    assert "ofi_ratio" in res_df.columns
    assert res_df["total_bid_depth"].iloc[0] == 60000.0
    assert res_df["total_ask_depth"].iloc[0] == 30000.0
    # ofi_ratio = (60000 - 30000) / (60000 + 30000) = 30000 / 90000 = 0.3333...
    assert pytest.approx(res_df["ofi_ratio"].iloc[0], 0.001) == 0.3333


def test_intraday_trades_shark_detection(temp_db):
    crawler = OrderBookDepthCrawler(db_path=temp_db)

    mock_trades = pd.DataFrame([
        {"time": "2026-09-17 10:00:00", "price": 21.0, "volume": 500, "match_type": "Buy", "id": "t1"},
        {"time": "2026-09-17 10:00:01", "price": 21.05, "volume": 50000, "match_type": "Buy", "id": "t2"},
        {"time": "2026-09-17 10:00:02", "price": 20.95, "volume": 30000, "match_type": "Sell", "id": "t3"},
    ])

    crawler.market.equity = MagicMock()
    crawler.market.equity.return_value.intraday.return_value = mock_trades

    res_df = crawler.fetch_intraday_trades("SSI")
    assert res_df is not None
    assert len(res_df) == 3
    assert not res_df.iloc[0]["is_shark_sweep"]
    assert res_df.iloc[1]["is_shark_sweep"]
    assert res_df.iloc[2]["is_shark_sweep"]
