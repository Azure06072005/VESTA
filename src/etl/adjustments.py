"""F009 item 4: OHLCV corporate-action price adjustment.

DECISION (2026-08-16, see DECISIONS.md): confirmed live that neither
`Market().equity(symbol).ohlcv()` nor `Quote(symbol=...).history()`
exposes an adjusted-price field or a split/dividend-adjustment parameter
-- vnstock's free tier does not provide this. Adjustment is therefore
computed DOWNSTREAM from F006's corporate_events data, not at crawl time,
and stored as a SEPARATE table (core.price_adjustment_events) rather than
mutating core.market_ohlcv_daily -- raw crawled prices are never
overwritten (raw-payload-preserving principle, formalized in F009 item 7).
Callers apply the adjustment at query/join time via apply_adjustment().

CONFIRMED live 2026-08-13 corporate-event fields relevant to price
adjustment (from F006's detail_json, not promoted to typed columns):
  - category == 'DIVIDEND', value_per_share populated -> cash dividend
  - event_code == 'ISS' (Share Issue), exercise_ratio populated ->
    bonus/rights share issuance. Vietnamese market convention represents
    what a US market would call a "stock split" as bonus share issuance;
    no distinct 'SPLIT' category was observed in the live discovery
    output, so this is the closest real signal available.
  - exright_date is the ex-rights/ex-dividend date used as the adjustment
    breakpoint (NOT display_date1, which F006 promotes as event_date and
    may be an announcement date rather than the ex-date).

Standard backward-adjustment convention: a multiplier computed at each
ex_date is applied to every OHLCV row STRICTLY BEFORE that ex_date, so
historical prices are expressed in "today's share count / net-of-dividend"
terms and become comparable across corporate actions.

**UNVALIDATED**: these formulas have NOT been checked against a real,
publicly known adjusted-price series for an actual Vietnamese stock. Do
not trust this in a live backtest until that validation happens -- see
DECISIONS.md 2026-08-16 entry.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402

ADJUSTMENT_EVENT_COLUMNS = ["symbol", "ex_date", "adjustment_type", "multiplier", "source_event_id", "computed_at"]


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("", "nan", "none"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def compute_adjustment_events(events_df: pd.DataFrame, ohlcv_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Pure transform: derive (ex_date, adjustment_type, multiplier) rows
    from F006's corporate_events rows (needs event_id, event_type,
    detail_json columns) and F002's OHLCV rows (needs date, close columns,
    only used to compute the cum-dividend reference price for cash
    dividends). No network access -- fully unit-testable.
    """
    if events_df.empty:
        return pd.DataFrame(columns=["ex_date", "adjustment_type", "multiplier", "source_event_id"])

    ohlcv_sorted = ohlcv_df.sort_values("date").reset_index(drop=True)
    rows = []

    for _, event in events_df.iterrows():
        try:
            detail = json.loads(event["detail_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        exright_date_str = detail.get("exright_date")
        if not exright_date_str or str(exright_date_str).strip().lower() in ("nan", "none", ""):
            continue
        try:
            ex_date = pd.to_datetime(exright_date_str).date()
        except (ValueError, TypeError):
            continue

        event_code = detail.get("event_code")
        exercise_ratio = _parse_float(detail.get("exercise_ratio"))
        value_per_share = _parse_float(detail.get("value_per_share"))

        if event_code == "ISS" and exercise_ratio is not None and exercise_ratio > 0:
            multiplier = 1.0 / (1.0 + exercise_ratio)
            adjustment_type = "share_issue"
        elif event.get("event_type") == "DIVIDEND" and value_per_share is not None and value_per_share > 0:
            prior_rows = ohlcv_sorted[ohlcv_sorted["date"] < ex_date]
            if prior_rows.empty:
                continue
            cum_close = float(prior_rows.iloc[-1]["close"])
            if cum_close <= value_per_share:
                # Dividend >= cum-dividend close -- can't produce a sane
                # positive multiplier. Skip rather than emit garbage.
                continue
            multiplier = (cum_close - value_per_share) / cum_close
            adjustment_type = "dividend"
        else:
            continue

        rows.append(
            {
                "ex_date": ex_date,
                "adjustment_type": adjustment_type,
                "multiplier": multiplier,
                "source_event_id": event["event_id"],
            }
        )

    return pd.DataFrame(rows, columns=["ex_date", "adjustment_type", "multiplier", "source_event_id"])


def write_adjustment_events(df: pd.DataFrame, symbol: str, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write. Idempotent on (symbol, ex_date, source_event_id)
    via primary key -- re-running with the same events is a no-op, not a
    duplicate.
    """
    if df.empty:
        return 0

    out = df.copy()
    out["symbol"] = symbol
    out["computed_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    out = out[ADJUSTMENT_EVENT_COLUMNS]

    con = con or db.bootstrap_schema()
    con.register("adj_df", out)
    con.execute(
        "INSERT INTO staging.price_adjustment_events SELECT * FROM adj_df "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM staging.price_adjustment_events s"
        "  WHERE s.symbol = adj_df.symbol AND s.ex_date = adj_df.ex_date"
        "    AND s.source_event_id = adj_df.source_event_id"
        ")"
    )
    con.execute(
        "INSERT INTO core.price_adjustment_events SELECT * FROM adj_df "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM core.price_adjustment_events s"
        "  WHERE s.symbol = adj_df.symbol AND s.ex_date = adj_df.ex_date"
        "    AND s.source_event_id = adj_df.source_event_id"
        ")"
    )
    con.unregister("adj_df")

    return len(out)


def get_adjustment_factor(adjustment_events_df: pd.DataFrame, as_of_date: dt.date) -> float:
    """Cumulative multiplier to apply to a raw price on as_of_date --
    product of every adjustment event with ex_date strictly after
    as_of_date (backward-adjustment convention: prices are expressed in
    terms of the most recent share count / net-of-dividend basis).
    """
    if adjustment_events_df.empty:
        return 1.0
    applicable = adjustment_events_df[adjustment_events_df["ex_date"] > as_of_date]
    if applicable.empty:
        return 1.0
    values = [float(v) for v in applicable["multiplier"].tolist()]
    product = 1.0
    for v in values:
        product *= v
    return product


def apply_adjustment(ohlcv_df: pd.DataFrame, adjustment_events_df: pd.DataFrame) -> pd.DataFrame:
    """Returns ohlcv_df with adj_open/adj_high/adj_low/adj_close columns
    added -- raw open/high/low/close/volume columns are untouched. This is
    what F102 should join against for backtest-ready prices, not the raw
    core.market_ohlcv_daily columns directly.
    """
    out = ohlcv_df.copy()
    out["adj_factor"] = out["date"].apply(lambda d: get_adjustment_factor(adjustment_events_df, d))
    for col in ("open", "high", "low", "close"):
        out[f"adj_{col}"] = out[col] * out["adj_factor"]
    return out