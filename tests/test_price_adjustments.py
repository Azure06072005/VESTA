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