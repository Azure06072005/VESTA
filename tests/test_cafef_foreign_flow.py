"""Unit tests for CafeF Foreign Investor Flow Ingester (cafef_foreign_flow.py)."""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from unittest.mock import patch

import duckdb
import pytest

from src.crawlers.cafef_foreign_flow import CafeFForeignFlowIngester


@pytest.fixture
def temp_duckdb(tmp_path):
    """Tạo database DuckDB test với schema core.market_foreign_flow_daily."""
    db_path = str(tmp_path / "test_foreign.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("""
        CREATE TABLE core.market_foreign_flow_daily (
            symbol VARCHAR NOT NULL,
            date DATE NOT NULL,
            buy_volume DOUBLE,
            sell_volume DOUBLE,
            buy_value DOUBLE,
            sell_value DOUBLE,
            net_volume DOUBLE,
            net_value DOUBLE,
            foreign_room DOUBLE,
            fetched_at TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)
    con.close()
    return db_path


def test_parse_nn_csv_standard():
    """Kiểm tra parse đúng cấu trúc CSV khối ngoại CafeF."""
    csv_data = (
        "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>,<OI>\n"
        "VCB,20260904,500000,200000,30000000,12000000,1000000,15000000\n"
    )
    df = CafeFForeignFlowIngester.parse_nn_csv(io.StringIO(csv_data))
    assert len(df) == 1
    assert df.loc[0, "symbol"] == "VCB"
    assert df.loc[0, "date"] == dt.date(2026, 9, 4)
    assert df.loc[0, "buy_volume"] == 500000.0
    assert df.loc[0, "sell_volume"] == 200000.0
    assert df.loc[0, "net_volume"] == 300000.0
    assert df.loc[0, "net_value"] == 18000000.0
    assert df.loc[0, "foreign_room"] == 15000000.0


def test_ingest_zip_stream_success(temp_duckdb):
    """Kiểm tra nạp dữ liệu khối ngoại vào DuckDB từ zip."""
    ingester = CafeFForeignFlowIngester(duckdb_path=temp_duckdb)

    csv_content = (
        "<Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>,<OI>\n"
        "HPG,20260904,1500000,800000,38000000,20000000,2500000,50000000\n"
        "FPT,20260904,600000,100000,81000000,13500000,1200000,20000000\n"
    ).encode("utf-8-sig")

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as z:
        z.writestr("CafeF.NN_HSX.04.09.2026.csv", csv_content)
    zip_buf.seek(0)

    with patch.object(ingester.session, "get") as mock_get:
        mock_resp = patch("requests.Response").start()
        mock_resp.status_code = 200
        mock_resp.content = zip_buf.getvalue()
        mock_get.return_value = mock_resp

        count = ingester.ingest_zip_stream("http://test.zip")
        assert count == 2

    con = duckdb.connect(temp_duckdb, read_only=True)
    rows = con.execute("SELECT symbol, net_volume, foreign_room FROM core.market_foreign_flow_daily ORDER BY symbol").fetchall()
    con.close()
    assert len(rows) == 2
    assert rows[0] == ("FPT", 500000.0, 20000000.0)
    assert rows[1] == ("HPG", 700000.0, 50000000.0)
