"""F009 item 4 verification.

Fixtures match the CONFIRMED real shapes: F006's corporate_events row
shape (event_id, event_type, detail_json containing exright_date/
event_code/exercise_ratio/value_per_share, per the real 2026-08-13
discovery output), and F002's OHLCV shape (date, open/high/low/close/
volume). No network access -- fully unit-testable.

UNVALIDATED against a real published adjusted-price series -- see
src/etl/adjustments.py module docstring and DECISIONS.md. These tests
confirm the arithmetic is internally consistent, not that it matches a
real market data vendor's numbers.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from etl import adjustments  # noqa: E402


def _sample_ohlcv_df() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=10, freq="D").date
    return pd.DataFrame(
        {
            "date": dates,
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1000] * 10,
        }
    )


def _dividend_event(event_id: str, exright_date: str, value_per_share: float) -> dict:
    return {
        "event_id": event_id,
        "event_type": "DIVIDEND",
        "detail_json": json.dumps(
            {
                "exright_date": exright_date,
                "event_code": "DIV",
                "exercise_ratio": "nan",
                "value_per_share": str(value_per_share),
            }
        ),
    }


def _share_issue_event(event_id: str, exright_date: str, exercise_ratio: float) -> dict:
    return {
        "event_id": event_id,
        "event_type": "OTHER",
        "detail_json": json.dumps(
            {
                "exright_date": exright_date,
                "event_code": "ISS",
                "exercise_ratio": str(exercise_ratio),
                "value_per_share": "nan",
            }
        ),
    }


def test_compute_adjustment_events_handles_share_issue():
    events_df = pd.DataFrame([_share_issue_event("EVT1", "2025-01-06", 0.10)])
    out = adjustments.compute_adjustment_events(events_df, _sample_ohlcv_df(), "FPT")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["adjustment_type"] == "share_issue"
    assert row["multiplier"] == pytest.approx(1.0 / 1.10)


def test_compute_adjustment_events_handles_dividend_using_prior_close():
    # cum-dividend close is 100.0 (from _sample_ohlcv_df), dividend = 5.0
    events_df = pd.DataFrame([_dividend_event("EVT2", "2025-01-06", 5.0)])
    out = adjustments.compute_adjustment_events(events_df, _sample_ohlcv_df(), "FPT")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["adjustment_type"] == "dividend"
    assert row["multiplier"] == pytest.approx((100.0 - 5.0) / 100.0)


def test_compute_adjustment_events_skips_events_without_exright_date():
    events_df = pd.DataFrame(
        [
            {
                "event_id": "EVT3",
                "event_type": "SHAREHOLDER_MEETING",
                "detail_json": json.dumps({"exright_date": "nan", "event_code": "AGME"}),
            }
        ]
    )
    out = adjustments.compute_adjustment_events(events_df, _sample_ohlcv_df(), "FPT")
    assert out.empty


def test_compute_adjustment_events_skips_dividend_exceeding_cum_close():
    # A malformed/implausible case -- dividend >= close price. Must not
    # produce a negative or zero multiplier.
    events_df = pd.DataFrame([_dividend_event("EVT4", "2025-01-06", 500.0)])
    out = adjustments.compute_adjustment_events(events_df, _sample_ohlcv_df(), "FPT")
    assert out.empty


def test_get_adjustment_factor_compounds_multiple_events():
    adj_events = pd.DataFrame(
        [
            {"ex_date": dt.date(2025, 6, 1), "multiplier": 0.9},
            {"ex_date": dt.date(2025, 9, 1), "multiplier": 0.8},
        ]
    )
    # A date before BOTH ex_dates gets both multipliers compounded.
    factor = adjustments.get_adjustment_factor(adj_events, dt.date(2025, 1, 1))
    assert factor == pytest.approx(0.9 * 0.8)

    # A date between the two ex_dates gets only the later one.
    factor_mid = adjustments.get_adjustment_factor(adj_events, dt.date(2025, 7, 1))
    assert factor_mid == pytest.approx(0.8)

    # A date after both ex_dates is unadjusted.
    factor_after = adjustments.get_adjustment_factor(adj_events, dt.date(2025, 12, 1))
    assert factor_after == pytest.approx(1.0)


def test_apply_adjustment_adds_columns_without_mutating_raw_prices():
    ohlcv = _sample_ohlcv_df()
    adj_events = pd.DataFrame([{"ex_date": dt.date(2025, 1, 6), "multiplier": 0.5}])
    out = adjustments.apply_adjustment(ohlcv, adj_events)

    assert "adj_close" in out.columns
    assert "close" in out.columns
    # Raw close is untouched.
    assert (out["close"] == 100.0).all()
    # Adjusted close reflects the 0.5 factor for dates before the ex_date.
    before = out[out["date"] < dt.date(2025, 1, 6)]
    assert (before["adj_close"] == 50.0).all()
    on_or_after = out[out["date"] >= dt.date(2025, 1, 6)]
    assert (on_or_after["adj_close"] == 100.0).all()


def test_write_adjustment_events_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    events_df = pd.DataFrame([_share_issue_event("EVT5", "2025-01-06", 0.10)])
    computed = adjustments.compute_adjustment_events(events_df, _sample_ohlcv_df(), "FPT")

    n1 = adjustments.write_adjustment_events(computed, "FPT", con)
    n2 = adjustments.write_adjustment_events(computed, "FPT", con)  # re-run, same input
    assert n1 == 1
    assert n2 == 1  # write_adjustment_events itself doesn't dedupe its return count,

    row_count = con.execute(
        "SELECT COUNT(*) FROM core.price_adjustment_events WHERE symbol = 'FPT'"
    ).fetchone()[0]
    assert row_count == 1  # but the DB-level idempotency guard prevents a real duplicate row


# =============================================================================
# F002 RECOMMENDATION TESTS: SSC FORMULA, CAF TIMELINE, DUAL-MODE VIEW
# =============================================================================

def test_compute_ssc_ex_price_pure_cash():
    """Kiểm tra công thức cổ tức tiền mặt: P_close=100, D=5 -> P_ex=95, f=0.95."""
    p_ex, f = adjustments.compute_ssc_ex_price(p_close=100.0, cash_dividend=5.0)
    assert p_ex == pytest.approx(95.0)
    assert f == pytest.approx(0.95)


def test_compute_ssc_ex_price_pure_stock():
    """Kiểm tra công thức thưởng cổ phiếu: P_close=100, alpha=0.25 -> P_ex=80, f=0.80."""
    p_ex, f = adjustments.compute_ssc_ex_price(p_close=100.0, stock_ratio=0.25)
    assert p_ex == pytest.approx(80.0)
    assert f == pytest.approx(0.80)


def test_compute_ssc_ex_price_combined():
    """Kiểm tra công thức gộp: P_close=100, D=2, alpha=0.20 -> P_ex=(100-2)/1.2=81.6667, f=0.816667."""
    p_ex, f = adjustments.compute_ssc_ex_price(p_close=100.0, cash_dividend=2.0, stock_ratio=0.20)
    assert p_ex == pytest.approx(98.0 / 1.2)
    assert f == pytest.approx((98.0 / 1.2) / 100.0)


def test_compute_ssc_ex_price_rights_issue():
    """Kiểm tra quyền mua ưu đãi: P_close=40, beta=0.5, P_add=10 -> P_ex=(40+5)/1.5=30, f=0.75."""
    p_ex, f = adjustments.compute_ssc_ex_price(
        p_close=40.0,
        rights_ratio=0.5,
        rights_price=10.0,
    )
    assert p_ex == pytest.approx(30.0)
    assert f == pytest.approx(0.75)


def test_compute_symbol_adjustments_timeline_intervals():
    """Kiểm tra sinh chuỗi CAF và khoảng timeline không chồng lấn [start_date, end_date)."""
    ohlcv = pd.DataFrame({
        "date": [dt.date(2025, 1, 1), dt.date(2025, 6, 1), dt.date(2025, 12, 1)],
        "close": [100.0, 100.0, 100.0],
    })
    events = pd.DataFrame([
        {
            "event_id": "E1",
            "event_type": "DIVIDEND",
            "detail_json": json.dumps({"exright_date": "2025-06-02", "event_code": "DIV", "value_per_share": 10000.0}), # D=10.0 nghìn
        },
        {
            "event_id": "E2",
            "event_type": "DIVIDEND",
            "detail_json": json.dumps({"exright_date": "2025-10-01", "event_code": "ISS", "exercise_ratio": 0.25}),      # alpha=0.25
        },
    ])

    df_adj, df_time = adjustments.compute_symbol_adjustments("TEST", events, ohlcv)
    assert len(df_adj) == 2
    # f1 = (100 - 10)/100 = 0.90
    # f2 = 1 / 1.25 = 0.80
    assert df_adj.iloc[0]["multiplier"] == pytest.approx(0.90)
    assert df_adj.iloc[1]["multiplier"] == pytest.approx(0.80)
    # CAF dồn: sự kiện 1 (cũ hơn) có CAF = 0.90 * 0.80 = 0.72; sự kiện 2 có CAF = 0.80
    assert df_adj.iloc[0]["cumulative_adjustment_factor"] == pytest.approx(0.72)
    assert df_adj.iloc[1]["cumulative_adjustment_factor"] == pytest.approx(0.80)

    # Timeline: 3 khoảng:
    # 1: [1990-01-01, 2025-06-02) -> caf = 0.72
    # 2: [2025-06-02, 2025-10-01) -> caf = 0.80
    # 3: [2025-10-01, 2099-12-31) -> caf = 1.00
    assert len(df_time) == 3
    assert df_time.iloc[0]["caf"] == pytest.approx(0.72)
    assert df_time.iloc[1]["caf"] == pytest.approx(0.80)
    assert df_time.iloc[2]["caf"] == pytest.approx(1.00)


def test_v_market_ohlcv_dual_query(tmp_path):
    """Kiểm tra view core.v_market_ohlcv_dual tính đúng giá thô và giá điều chỉnh song song."""
    db_path = tmp_path / "test_dual.duckdb"
    con = db.bootstrap_schema(db_path)

    # Nạp nến mẫu vào core.market_ohlcv_daily
    con.execute("""
        INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume, fetched_at)
        VALUES 
            ('TEST', DATE '2025-01-02', 72.0, 75.0, 70.0, 72.0, 1000000, CURRENT_TIMESTAMP),
            ('TEST', DATE '2025-07-01', 80.0, 82.0, 78.0, 80.0, 1000000, CURRENT_TIMESTAMP),
            ('TEST', DATE '2025-11-01', 100.0, 102.0, 99.0, 100.0, 1000000, CURRENT_TIMESTAMP);
    """)

    # Nạp timeline vào core.symbol_caf_timeline
    con.execute("""
        INSERT INTO core.symbol_caf_timeline (symbol, start_date, end_date, caf)
        VALUES 
            ('TEST', DATE '1990-01-01', DATE '2025-06-02', 0.72),
            ('TEST', DATE '2025-06-02', DATE '2025-10-01', 0.80),
            ('TEST', DATE '2025-10-01', DATE '2099-12-31', 1.00);
    """)

    res = con.execute("""
        SELECT date, adj_close, caf, raw_close, adj_volume, raw_volume
        FROM core.v_market_ohlcv_dual
        WHERE symbol = 'TEST'
        ORDER BY date
    """).fetchall()

    assert len(res) == 3
    # Row 1 (2025-01-02): caf=0.72 -> raw_close = 72.0 / 0.72 = 100.0, raw_volume = 1,000,000 * 0.72 = 720,000
    assert res[0][1] == pytest.approx(72.0)
    assert res[0][2] == pytest.approx(0.72)
    assert res[0][3] == pytest.approx(100.0)
    assert res[0][5] == pytest.approx(720000)

    # Row 2 (2025-07-01): caf=0.80 -> raw_close = 80.0 / 0.80 = 100.0, raw_volume = 800,000
    assert res[1][1] == pytest.approx(80.0)
    assert res[1][2] == pytest.approx(0.80)
    assert res[1][3] == pytest.approx(100.0)
    assert res[1][5] == pytest.approx(800000)

    # Row 3 (2025-11-01): caf=1.00 -> raw_close = 100.0, raw_volume = 1,000,000
    assert res[2][1] == pytest.approx(100.0)
    assert res[2][2] == pytest.approx(1.00)
    assert res[2][3] == pytest.approx(100.0)
    assert res[2][5] == pytest.approx(1000000)

    con.close()