"""
Unit tests for Tiered Validation Penalty Framework (F101 recommendation).
"""
import datetime as dt
import duckdb
import pytest
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pipeline.tiered_validation import (
    evaluate_event_dqs,
    audit_tiered_quality,
    TIER_A_PRISTINE,
    TIER_B_USABLE,
    TIER_C_DEGRADED,
    TIER_1_REJECT,
)


def test_pristine_record_scores_high():
    record = {
        "price_at_publish": 50.0,
        "price_t1": 51.0,
        "price_t5": 52.5,
        "price_t30": 55.0,
        "published_at": dt.datetime(2026, 5, 10, 10, 30, 0),
        "fetched_at": dt.datetime(2026, 5, 10, 10, 31, 0),
        "body": "Doanh thu CTCP FPT quý 1 năm 2026 tăng trưởng 20% so với cùng kỳ năm trước nhờ khối công nghệ thông tin toàn cầu.",
        "fundamentals_json": '{"pe": 15.2, "roe": 0.25}',
        "pub_time": "10:30:00",
    }
    dqs, flags, tier = evaluate_event_dqs(record)
    assert dqs == 1.0
    assert flags == "CLEAN"
    assert tier == TIER_A_PRISTINE


def test_tier1_zero_price_rejects_immediately():
    record = {
        "price_at_publish": 0.0,  # Invalid price!
        "price_t1": 10.0,
        "price_t5": 10.5,
        "published_at": dt.datetime(2026, 5, 10, 10, 30, 0),
        "fetched_at": dt.datetime(2026, 5, 10, 10, 31, 0),
    }
    dqs, flags, tier = evaluate_event_dqs(record)
    assert dqs == 0.0
    assert "TIER1_ZERO_PRICE" in flags
    assert tier == TIER_1_REJECT


def test_tier1_lookahead_timing_rejects():
    record = {
        "price_at_publish": 25.0,
        "price_t1": 25.5,
        "published_at": dt.datetime(2026, 5, 10, 15, 0, 0),
        "fetched_at": dt.datetime(2026, 5, 10, 10, 0, 0),  # fetched before published!
    }
    dqs, flags, tier = evaluate_event_dqs(record)
    assert dqs == 0.0
    assert "TIER1_LOOKAHEAD_TIMING" in flags
    assert tier == TIER_1_REJECT


def test_tier3_headline_only_and_missing_bctc_penalized_but_usable():
    # Record has valid price and valid trade horizons, but headline only and missing BCTC
    record = {
        "price_at_publish": 30.0,
        "price_t1": 30.2,
        "price_t5": 31.0,
        "price_t30": 32.0,
        "published_at": dt.datetime(2026, 5, 10, 9, 15, 0),
        "fetched_at": dt.datetime(2026, 5, 10, 9, 16, 0),
        "body": None,  # Headline only -> -0.15
        "fundamentals_json": "{}",  # Missing BCTC -> -0.15
        "pub_time": "09:15:00",
    }
    dqs, flags, tier = evaluate_event_dqs(record)
    assert dqs == 0.70  # 1.0 - 0.15 - 0.15 = 0.70
    assert "TIER3_HEADLINE_ONLY" in flags
    assert "TIER3_MISSING_BCTC" in flags
    assert tier == TIER_B_USABLE


def test_tier3_midnight_timestamp_penalized():
    record = {
        "price_at_publish": 30.0,
        "price_t1": 30.2,
        "price_t5": 31.0,
        "price_t30": 32.0,
        "published_at": dt.datetime(2026, 5, 10, 0, 0, 0),
        "fetched_at": dt.datetime(2026, 5, 10, 6, 0, 0),
        "body": "Đầy đủ nội dung bài viết phân tích chi tiết kết quả kinh doanh quý 2 năm 2026 của doanh nghiệp.",
        "fundamentals_json": '{"pe": 12.0}',
        "pub_time": "00:00:00",  # Midnight -> -0.20
    }
    dqs, flags, tier = evaluate_event_dqs(record)
    assert dqs == 0.80  # 1.0 - 0.20 = 0.80
    assert "TIER3_MIDNIGHT_TIMESTAMP" in flags
    assert tier == TIER_B_USABLE


def test_audit_tiered_quality_in_memory():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA core")
    con.execute("ATTACH ':memory:' AS news_db")
    con.execute("CREATE SCHEMA news_db.core")

    con.execute("""
        CREATE TABLE core.pit_events (
            symbol VARCHAR,
            source_url VARCHAR,
            price_at_publish DOUBLE,
            price_t1 DOUBLE,
            price_t5 DOUBLE,
            price_t30 DOUBLE,
            fundamentals_json VARCHAR
        );
        CREATE TABLE news_db.core.news (
            source_url VARCHAR,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP,
            body VARCHAR
        );
    """)

    # Seed 2 records: 1 pristine, 1 reject
    con.execute("""
        INSERT INTO core.pit_events VALUES 
        ('FPT', 'url1', 100.0, 101.0, 102.0, 105.0, '{"pe": 15}'),
        ('HPG', 'url2', 0.0, 25.0, 26.0, 27.0, '{}');

        INSERT INTO news_db.core.news VALUES
        ('url1', '2026-05-10 10:00:00', '2026-05-10 10:05:00', 'Chi tiết bài viết phân tích cổ phiếu FPT với hơn 50 ký tự nội dung đầy đủ.'),
        ('url2', '2026-05-10 11:00:00', '2026-05-10 11:05:00', 'Tin ngắn HPG');
    """)

    res = audit_tiered_quality(con, sample_size=10)
    assert res["sample_size"] == 2
    assert res["reject_rate"] == 0.5
    assert TIER_A_PRISTINE in res["tier_distribution"]
    assert TIER_1_REJECT in res["tier_distribution"]
