"""F101 verification.

Per the feature spec: 'fails loudly on a deliberately injected orphan
symbol.' The core property under test is exactly that -- inject a bad
symbol, confirm validate_or_raise() actually raises, confirm a clean
database passes silently.
"""
from __future__ import annotations

import datetime as dt
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from etl import db  # noqa: E402
from pipeline import validate_crossref as vcr  # noqa: E402


def _seed_dim_symbol(con, symbols: list[str]) -> None:
    for s in symbols:
        con.execute(
            "INSERT INTO core.dim_symbol (symbol, organ_name, fetched_at) VALUES (?, ?, ?)",
            [s, f"{s} Corp", dt.datetime(2026, 1, 1)],
        )


def test_clean_database_passes_validation(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES "
        "('FPT', '2026-01-01', 100, 101, 99, 100, 1000, '2026-01-01 00:00:00')"
    )
    validate_crossref_should_not_raise = vcr.validate_or_raise
    validate_crossref_should_not_raise(con)  # must not raise


def test_orphan_symbol_in_ohlcv_raises_validation_error(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    # Deliberately injected orphan: XYZ never appears in core.dim_symbol.
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES "
        "('XYZ', '2026-01-01', 100, 101, 99, 100, 1000, '2026-01-01 00:00:00')"
    )
    with pytest.raises(vcr.ValidationError, match="orphan symbols"):
        vcr.validate_or_raise(con)


def test_orphan_symbol_reported_for_the_correct_table(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    con.execute(
        "INSERT INTO core.news (symbol, source, published_at, available_at, headline, body, source_url, fetched_at) VALUES "
        "('BADSYM','vnstock','2026-01-01 00:00:00','2026-01-01 00:00:00','H',NULL,'u1','2026-01-01 00:00:00')"
    )
    report = vcr.run_validation(con)
    assert report["orphan_symbols"] == {"core.news": ["BADSYM"]}


def test_future_fetched_at_raises_validation_error(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    far_future = (dt.datetime.now() + dt.timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")
    con.execute(
        f"INSERT INTO core.market_ohlcv_daily VALUES "
        f"('FPT', '2026-01-01', 100, 101, 99, 100, 1000, '{far_future}')"
    )
    with pytest.raises(vcr.ValidationError, match="future-dated rows"):
        vcr.validate_or_raise(con)


def test_orphan_adjustment_event_raises_validation_error(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    # No matching core.corporate_events row for this source_event_id.
    con.execute(
        "INSERT INTO core.price_adjustment_events VALUES "
        "('FPT', '2026-01-01', 'dividend', 0.95, 'NONEXISTENT_EVENT_ID', '2026-01-01 00:00:00')"
    )
    with pytest.raises(vcr.ValidationError, match="no matching corporate_events row"):
        vcr.validate_or_raise(con)


def test_adjustment_event_with_real_corporate_event_passes(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    con.execute(
        "INSERT INTO core.corporate_events VALUES "
        "('FPT', 'EVT1', 'DIVIDEND', '2026-01-01', '{}', '2026-01-01 00:00:00')"
    )
    con.execute(
        "INSERT INTO core.price_adjustment_events VALUES "
        "('FPT', '2026-01-01', 'dividend', 0.95, 'EVT1', '2026-01-01 00:00:00')"
    )
    vcr.validate_or_raise(con)  # must not raise


def test_run_validation_skips_tables_that_do_not_exist_yet():
    # get_valid_symbols/find_orphan_symbols must not blow up if a future
    # feature's table (e.g. F102's events table) doesn't exist yet --
    # confirmed here by running against a bootstrap_schema() DB that only
    # has the currently-defined tables, none of which are missing, so this
    # mainly guards the existence check itself doesn't false-positive.
    import duckdb

    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA core")
    con.execute(
        "CREATE TABLE core.dim_symbol (symbol VARCHAR, organ_name VARCHAR, en_organ_name VARCHAR, "
        "exchange VARCHAR, industry_code VARCHAR, industry_name VARCHAR, delisted_date DATE, "
        "fetched_at TIMESTAMP, PRIMARY KEY (symbol))"
    )
    report = vcr.run_validation(con)
    assert report["orphan_symbols"] == {}
    assert report["future_timestamps"] == {}
    assert report["orphan_adjustment_events"] == []


def test_dim_symbol_cafef_symbols_recognized_as_valid(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    con.execute(
        "INSERT INTO core.dim_symbol_cafef (symbol, org_name, exchange, center_id, is_vn30, is_hnx30, slug_base, source, fetched_at, raw_json) "
        "VALUES ('BAM', 'BAM Minerals', 'UPCOM', 9, false, false, '/du-lieu/bam', 'cafef', '2026-01-01 00:00:00', '{}')"
    )
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES "
        "('BAM', '2026-01-01', 10, 11, 9, 10, 500, '2026-01-01 00:00:00')"
    )
    vcr.validate_or_raise(con)  # must not raise


def test_known_non_equity_patterns_and_allowlist_pass_validation(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    # Covered warrant, corporate bond, HNX derivative, ETF, index, documented residual equity
    known_symbols = ["CHPG2541", "BID122005", "41I1G9000", "E1VFVN30", "VNX-ALL", "TCS"]
    for s in known_symbols:
        con.execute(
            f"INSERT INTO core.market_ohlcv_daily VALUES "
            f"('{s}', '2026-01-01', 10, 11, 9, 10, 100, '2026-01-01 00:00:00')"
        )
    vcr.validate_or_raise(con)  # must not raise


def test_unknown_symbol_still_fails_loudly(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test.duckdb")
    _seed_dim_symbol(con, ["FPT"])
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES "
        "('TOTALLY_BOGUS', '2026-01-01', 10, 11, 9, 10, 100, '2026-01-01 00:00:00')"
    )
    with pytest.raises(vcr.ValidationError, match="orphan symbols"):
        vcr.validate_or_raise(con)


def test_non_equity_patterns_zero_false_positives_on_known_equity_shapes():
    """Guards against regressions where a real equity (e.g. OTC names like
    CARLSBERG, FUTA, E12, CIENCO1) matches a non-equity exception pattern.
    """
    from pipeline.symbol_classification import is_known_non_dim_symbol

    test_equity_tickers = [
        "FPT", "VIC", "VNM", "MWG", "TCB", "HPG", "SSI",
        # Tricky OTC tickers that start with C or FU or E1
        "CARLSBERG", "COKHIOTO32", "CHIPSANG", "CONSTREXIM", "CIENCO1",
        "CIENCO8", "FUTA", "CIENCO6", "CAPQUANG", "CASEAMIEX", "CIPUTRAHN",
        "CADISUN", "CIENCO5", "CTGROUP", "COCACOLA", "CALOFIC", "CARGILL",
        "E12", "COOPBANK", "CATHAYLIFE",
    ]
    false_positives = [s for s in test_equity_tickers if is_known_non_dim_symbol(s)]
    assert false_positives == [], f"Unexpected false positives among real equity tickers: {false_positives}"