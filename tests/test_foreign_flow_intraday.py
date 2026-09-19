"""Unit tests for ForeignFlowIntradayCrawler."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.crawlers.foreign_flow_intraday import ForeignFlowIntradayCrawler


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test.duckdb")


def test_foreign_flow_schema_init(temp_db):
    crawler = ForeignFlowIntradayCrawler(db_path=temp_db)
    import duckdb
    c = duckdb.connect(str(crawler.db_path), read_only=True)
    tables = c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'core'").fetchall()
    table_names = [t[0] for t in tables]
    assert "foreign_flow_intraday" in table_names
    assert "foreign_ownership_room" in table_names
    c.close()


def test_foreign_flow_fetch_and_save(temp_db):
    crawler = ForeignFlowIntradayCrawler(db_path=temp_db)

    mock_quote = pd.DataFrame([{
        "foreign_buy_volume": 500000.0,
        "foreign_sell_volume": 200000.0,
        "close_price": 21.5
    }])
    mock_summary = pd.DataFrame([{
        "foreign_ownership_pct": 34.5
    }])

    crawler.market.equity = MagicMock()
    crawler.market.equity.return_value.quote.return_value = mock_quote
    crawler.market.equity.return_value.summary.return_value = mock_summary

    rec = crawler.fetch_symbol_foreign("SSI")
    assert rec is not None
    assert rec["foreign_buy_volume"] == 500000.0
    assert rec["foreign_sell_volume"] == 200000.0
    assert rec["foreign_net_volume"] == 300000.0
    assert rec["foreign_ownership_pct"] == 34.5

    success = crawler.save_and_promote(rec)
    assert success

    import duckdb
    c = duckdb.connect(str(crawler.db_path), read_only=True)
    row = c.execute("SELECT symbol, foreign_net_volume, foreign_ownership_pct FROM core.foreign_ownership_room WHERE symbol = 'SSI'").fetchone()
    assert row is not None
    assert row[0] == "SSI"
    assert row[1] == 300000.0
    assert row[2] == 34.5
    c.close()
