"""tests/test_financial_notes.py

Unit tests for FinancialNotesCrawler.
Verifies fetching, schema mapping, staging insertion, and core promotion.
"""
from pathlib import Path
import tempfile
import duckdb
import pandas as pd
import pytest
from unittest.mock import patch

from src.crawlers.financial_notes import FinancialNotesCrawler


@pytest.fixture
def temp_duckdb():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tf:
        temp_path = tf.name
    Path(temp_path).unlink(missing_ok=True)
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


def test_financial_notes_init_and_promote(temp_duckdb):
    crawler = FinancialNotesCrawler(db_path=temp_duckdb)

    # Fake financial notes dataframe
    fake_notes_df = pd.DataFrame([
        {
            "symbol": "VCB",
            "period": "2026-Q2",
            "note_id": "NT_BS_DEBT_SECURITIES",
            "note_name": "Chứng khoán nợ",
            "item_order": 2,
            "item_level": 2,
            "unit": "VNĐ",
            "value": 2.005151e+13,
            "fetched_at": pd.Timestamp.now(),
        },
        {
            "symbol": "VCB",
            "period": "2026-Q2",
            "note_id": "NT_BS_LOANS_TO_CUSTOMERS",
            "note_name": "Cho vay khách hàng",
            "item_order": 5,
            "item_level": 1,
            "unit": "VNĐ",
            "value": 1.450000e+15,
            "fetched_at": pd.Timestamp.now(),
        }
    ])

    with patch.object(crawler, "fetch_symbol_notes", return_value=fake_notes_df):
        res = crawler.run(["VCB"], delay_sec=0.0)
        assert res["success_symbols"] == 1
        assert res["total_rows_promoted"] == 2

    # Verify DuckDB core.financial_notes
    con = duckdb.connect(temp_duckdb, read_only=True)
    df_core = con.execute("SELECT * FROM core.financial_notes WHERE symbol = 'VCB' ORDER BY item_order").df()
    assert len(df_core) == 2
    assert df_core.iloc[0]["note_id"] == "NT_BS_DEBT_SECURITIES"
    assert df_core.iloc[0]["value"] == 2.005151e+13

    # Verify meta.crawl_progress
    df_meta = con.execute("SELECT * FROM meta.crawl_progress WHERE dataset_name = 'financial_notes' AND symbol = 'VCB'").df()
    assert len(df_meta) == 1
    assert df_meta.iloc[0]["status"] == "success"
    con.close()
