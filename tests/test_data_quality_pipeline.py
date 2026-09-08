"""Tests for Enterprise 11-Technique Data Validation & Quality Pipeline."""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from etl import db  # noqa: E402
from pipeline.data_quality import DataQualityPipeline, generate_report  # noqa: E402


def _seed_basic_db(con):
    con.execute("INSERT INTO core.dim_symbol (symbol, organ_name, fetched_at) VALUES ('FPT', 'FPT Corp', '2026-01-01')")
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES ('FPT', '2026-01-02', 100.0, 105.0, 99.0, 102.0, 500000, '2026-01-02 16:00:00')"
    )
    con.execute(
        "INSERT INTO core.news (symbol, source, source_url, published_at, available_at, headline, fetched_at) VALUES "
        "('FPT', 'vnstock', 'https://example.com/fpt1', '2026-01-02 10:00:00', '2026-01-02', 'FPT Loi Nhuan Tang Truong', '2026-01-02 11:00:00')"
    )
    con.execute(
        "INSERT INTO core.fundamentals (symbol, report_type, period_end, available_at, data_json, fetched_at, source) "
        "VALUES ('FPT', 'balance_sheet', '2025-09-30', '2025-10-30', '{\"BS_TOTAL_ASSETS\": 1000, \"BS_TOTAL_LIABILITIES_AND_EQUITY\": 1000}', '2025-11-01', 'vnstock_data')"
    )
    con.execute(
        "INSERT INTO staging.pit_events VALUES ('FPT', 'https://example.com/fpt1', '2026-01-02 10:00:00', 'FPT Loi Nhuan Tang Truong', NULL, 102.0, 103.0, 105.0, 110.0, NULL, NULL, '2026-01-02 12:00:00')"
    )
    con.execute(
        "INSERT INTO core.pit_events VALUES ('FPT', 'https://example.com/fpt1', '2026-01-02 10:00:00', 'FPT Loi Nhuan Tang Truong', NULL, 102.0, 103.0, 105.0, 110.0, NULL, NULL, '2026-01-02 12:00:00')"
    )


def test_clean_synthetic_db_passes_data_quality_pipeline(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)

    pipeline = DataQualityPipeline(con)
    results = pipeline.run_all_techniques()
    profile = pipeline.profile_data()
    report = generate_report(results, profile)

    assert report["summary"]["status"] in ("PASS", "WARN")
    assert report["summary"]["errors"] == 0
    assert len(report["by_technique"]) >= 10
    assert "market_ohlcv_daily" in profile


def test_technique_1_data_type_validation_detects_malformed_json(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject non-JSON string into data_json
    con.execute(
        "INSERT INTO core.fundamentals (symbol, report_type, period_end, available_at, data_json, fetched_at, source) "
        "VALUES ('FPT', 'income_statement', '2025-12-31', '2026-01-15', '{malformed_json: true', '2026-01-16', 'vnstock_data')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_data_types()
    json_check = next(r for r in results if r.check_name == "fundamentals_json_type_validity")
    assert not json_check.passed
    assert json_check.metrics["invalid_json_rows"] == 1


def test_technique_2_range_validation_flags_negative_volume(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject negative volume
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES ('FPT', '2026-01-03', 100.0, 105.0, 99.0, 102.0, -500, '2026-01-03')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_range()
    range_check = next(r for r in results if r.check_name == "ohlcv_numeric_range_bounds")
    assert not range_check.passed
    assert range_check.metrics["negative_volume"] == 1


def test_technique_3_format_validation_flags_bad_urls(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject invalid URL scheme
    con.execute(
        "INSERT INTO core.news (symbol, source, source_url, published_at, available_at, headline, fetched_at) VALUES "
        "('FPT', 'vnstock', 'ftp://bad-scheme.com/file', '2026-01-03', '2026-01-03', 'Tin Moi', '2026-01-03')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_format()
    url_check = next(r for r in results if r.check_name == "news_source_url_protocol_format")
    assert not url_check.passed
    assert url_check.metrics["invalid_url_protocol_count"] == 1


def test_technique_4_presence_flags_empty_headlines(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject empty headline
    con.execute(
        "INSERT INTO core.news (symbol, source, source_url, published_at, available_at, headline, fetched_at) VALUES ('FPT', 'vnstock', 'u2', '2026-01-03', '2026-01-03', '', '2026-01-03')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_presence()
    headline_check = next(r for r in results if r.check_name == "news_required_fields_present")
    assert not headline_check.passed
    assert headline_check.metrics["empty_headline"] == 1


def test_technique_5_pattern_matching_flags_invalid_symbols(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject symbol containing illegal characters (lowercase or special symbols)
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES ('fpt$bad', '2026-01-03', 100.0, 105.0, 99.0, 102.0, 1000, '2026-01-03')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_pattern_matching()
    pat_check = next(r for r in results if r.check_name == "symbol_regex_pattern_matching")
    assert not pat_check.passed
    assert pat_check.metrics["pattern_violations"] == 1


def test_technique_6_cross_field_flags_inverted_candles(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject candle with high < low (impossible candle)
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES ('FPT', '2026-01-03', 100.0, 90.0, 110.0, 95.0, 1000, '2026-01-03')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_cross_field()
    candle_check = next(r for r in results if r.check_name == "candlestick_geometry_cross_field")
    assert not candle_check.passed
    assert candle_check.metrics["critical_violations"] == 1


def test_technique_7_uniqueness_flags_pk_duplicates(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Confirm primary key prevents duplicate insertion into market_ohlcv_daily
    with pytest.raises(Exception) as exc_info:
        con.execute("INSERT INTO core.market_ohlcv_daily VALUES ('FPT', '2026-01-02', 100, 105, 99, 102, 100, '2026-01-02')")
    assert "violates primary key" in str(exc_info.value) or "Constraint Error" in str(exc_info.value)


def test_technique_8_data_profiling_structure(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)

    pipeline = DataQualityPipeline(con)
    profile = pipeline.profile_data()

    assert "market_ohlcv_daily" in profile
    assert profile["market_ohlcv_daily"]["row_count"] == 1
    assert profile["market_ohlcv_daily"]["distinct_symbols"] == 1
    assert profile["market_ohlcv_daily"]["close_distribution"]["avg"] == 102.0
    assert profile["news"]["total_articles"] == 1


def test_technique_9_statistical_validation_detects_lookahead_leakage(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Add next day OHLCV
    con.execute("INSERT INTO core.market_ohlcv_daily VALUES ('FPT', '2026-01-05', 103.0, 108.0, 102.0, 107.0, 600000, '2026-01-05 16:00:00')")
    # Add after-hours news published at 16:30 anchoring to same day close (102.0) instead of next day close (107.0)
    con.execute(
        "INSERT INTO core.pit_events VALUES ('FPT', 'https://example.com/leakage', '2026-01-02 16:30:00', 'Tin Chieu', NULL, 102.0, 107.0, 107.0, 107.0, NULL, NULL, '2026-01-02 17:00:00')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_statistical_validation()
    leak_check = next(r for r in results if r.check_name == "zero_lookahead_bias_market_close_anchor")
    assert not leak_check.passed
    assert leak_check.metrics["leakage_violations"] == 1


def test_technique_10_business_rules_detects_premature_bctc_disclosure(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject premature fundamental filing (available_at before period_end)
    con.execute(
        "INSERT INTO core.fundamentals (symbol, report_type, period_end, available_at, data_json, fetched_at, source) "
        "VALUES ('FPT', 'income_statement', '2025-12-31', '2025-10-01', '{\"revenue\": 100}', '2025-10-02', 'vnstock_data')"
    )

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_business_rules()
    temporal_check = next(r for r in results if r.check_name == "fundamental_disclosure_temporal_order")
    assert not temporal_check.passed
    assert temporal_check.metrics["premature_disclosures"] == 1


def test_technique_11_external_validation_flags_unexplained_orphans(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_dq.duckdb")
    _seed_basic_db(con)
    # Inject orphan symbol into market_ohlcv_daily
    con.execute("INSERT INTO core.market_ohlcv_daily VALUES ('UNKNOWN999', '2026-01-03', 100, 105, 99, 102, 100, '2026-01-03')")

    pipeline = DataQualityPipeline(con)
    results = pipeline.check_external_validation()
    ref_check = next(r for r in results if r.check_name == "referential_integrity_symbols")
    assert not ref_check.passed
    assert ref_check.metrics["unexplained_orphans_count"] == 1
