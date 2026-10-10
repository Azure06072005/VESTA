"""tests/test_multi_asset_crawler.py

Unit tests for F073-F076 Multi-Asset Crawler Suite:
- F073: Derivatives (VN30 Index Futures)
- F074: Covered Warrants (CW on HOSE)
- F075: Exchange Traded Funds (ETFs)
- F076: Corporate & Government Bonds
"""
import duckdb
import pytest
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from crawlers.multi_asset_crawler import (
    crawl_derivatives,
    crawl_covered_warrants,
    crawl_etfs,
    crawl_bonds,
    fetch_derivative_bars,
)


def test_f073_derivatives_ingestion(tmp_path):
    test_db = str(tmp_path / "test_ohlcv.duckdb")
    cnt = crawl_derivatives(target_db=test_db)
    assert cnt > 0, "F073: Phải cào được nến phái sinh VN30 futures"

    con = duckdb.connect(test_db, read_only=True)
    rows = con.execute("SELECT count(*), count(DISTINCT symbol) FROM core.market_derivatives_daily").fetchone()
    assert rows[0] >= cnt
    assert rows[1] >= 1, "Phải có ít nhất 1 mã phái sinh"
    con.close()


def test_f074_covered_warrants_ingestion(tmp_path):
    test_db = str(tmp_path / "test_ohlcv.duckdb")
    cnt = crawl_covered_warrants(limit=5, target_db=test_db)
    assert cnt > 0, "F074: Phải cào được nến chứng quyền"

    con = duckdb.connect(test_db, read_only=True)
    rows = con.execute("SELECT count(*), count(DISTINCT symbol) FROM core.market_covered_warrants_daily").fetchone()
    assert rows[0] >= cnt
    con.close()


def test_f075_etfs_ingestion(tmp_path):
    test_db = str(tmp_path / "test_ohlcv.duckdb")
    cnt = crawl_etfs(target_db=test_db)
    assert cnt > 0, "F075: Phải cào được nến quỹ ETF"

    con = duckdb.connect(test_db, read_only=True)
    rows = con.execute("SELECT count(*), count(DISTINCT symbol) FROM core.market_etf_daily").fetchone()
    assert rows[0] >= cnt
    con.close()


def test_f076_bonds_ingestion(tmp_path):
    test_db = str(tmp_path / "test_ohlcv.duckdb")
    cnt = crawl_bonds(target_db=test_db)
    assert cnt > 0, "F076: Phải cào được danh mục trái phiếu"

    con = duckdb.connect(test_db, read_only=True)
    rows = con.execute("SELECT count(*) FROM core.market_bonds_daily").fetchone()
    assert rows[0] >= cnt
    con.close()
