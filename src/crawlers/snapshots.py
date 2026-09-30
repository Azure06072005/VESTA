"""F007: Realtime quote snapshot & market analytics crawler.

Architecture Upgrade (2026-09-27):
- Transitioned to Direct REST API architecture (Zero vnstock / Zero API Key).
- Primary Source: Vietcap Direct REST API (https://trading.vietcap.com.vn/api/price/symbols/getList)
  Returns confirmed 82+ column MultiIndex structure (listing, bid_ask, match) with full Top 3 Bid/Ask depth.
- Fallback Source: CafeF Realtime Prices API (https://cafef.vn/du-lieu/Ajax/PageNew/RealtimePricesHeader.ashx)
- Valuation Extension: CafeF Financial Indicators API (ChiSoTaiChinh.ashx) for real-time P/E, P/B, EPS.
- Retention: ACCUMULATE policy (one row per (symbol, snapshot_at), never overwritten).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

import duckdb
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402

logger = logging.getLogger("snapshots")

# CONFIRMED live: the real symbol column after flattening the MultiIndex is 'listing_symbol'.
# Aliases kept for robustness against a flat (non-MultiIndex) response.
SYMBOL_COLUMN_ALIASES = ["listing_symbol", "symbol", "ticker"]
SNAPSHOT_COLUMNS = ["symbol", "snapshot_at", "data_json", "fetched_at"]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _camel_to_snake(s: str) -> str:
    """Converts camelCase string to snake_case."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def fetch_raw_vietcap(symbols: list[str], timeout: int = 12) -> pd.DataFrame:
    """Direct REST call to Vietcap Securities price board API.
    Zero vnstock dependency, zero API key requirement.
    """
    url = "https://trading.vietcap.com.vn/api/price/symbols/getList"
    headers = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/json",
        "Referer": "https://trading.vietcap.com.vn/",
        "Origin": "https://trading.vietcap.com.vn/",
    }
    payload = json.dumps({"symbols": [s.upper() for s in symbols]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_items = json.loads(resp.read().decode("utf-8"))

    if not raw_items or not isinstance(raw_items, list):
        raise EmptyResultError(f"Vietcap API returned no data for symbols: {symbols}")

    rows: list[dict[str, Any]] = []
    for item in raw_items:
        row: dict[str, Any] = {}
        for k, v in item.get("listingInfo", {}).items():
            row[f"listing_{k}"] = v
        for k, v in item.get("matchPrice", {}).items():
            row[f"match_{k}"] = v
        bid_ask = item.get("bidAsk", {})
        for k, v in bid_ask.items():
            if k not in ("bidPrices", "askPrices"):
                row[f"bidAsk_{k}"] = v
        for i, b in enumerate(bid_ask.get("bidPrices", []), 1):
            row[f"bidAsk_bid_{i}_price"] = b.get("price")
            row[f"bidAsk_bid_{i}_volume"] = b.get("volume")
        for i, a in enumerate(bid_ask.get("askPrices", []), 1):
            row[f"bidAsk_ask_{i}_price"] = a.get("price")
            row[f"bidAsk_ask_{i}_volume"] = a.get("volume")
        rows.append(row)

    df = pd.DataFrame(rows)
    df.columns = pd.MultiIndex.from_tuples([
        tuple(_camel_to_snake(p) for p in col.split("_", 1)) for col in df.columns
    ])

    if ("listing", "board") in df.columns:
        df = df.rename(columns={"board": "exchange"}, level=1)

    df.attrs["source"] = "VIETCAP_DIRECT"
    return df


def fetch_raw_cafef(symbols: list[str], timeout: int = 10) -> pd.DataFrame:
    """Direct REST call to CafeF Realtime Prices API as fallback.
    Zero vnstock dependency, zero API key requirement.
    """
    if len(symbols) > 50:
        frames = []
        for i in range(0, len(symbols), 50):
            chunk = symbols[i : i + 50]
            try:
                df_chunk = fetch_raw_cafef(chunk, timeout=timeout)
                frames.append(df_chunk)
            except Exception as e:
                logger.warning("CafeF chunk %d-%d failed: %s", i, i + len(chunk), e)
        if not frames:
            raise EmptyResultError(f"CafeF returned no valid items for symbols: {symbols}")
        res = pd.concat(frames, ignore_index=True)
        res.attrs["source"] = "CAFEF_DIRECT"
        return res

    sym_str = ";".join(s.upper() for s in symbols)
    url = f"https://cafef.vn/du-lieu/Ajax/PageNew/RealtimePricesHeader.ashx?symbols={urllib.parse.quote(sym_str)}"
    headers = {
        **DEFAULT_HEADERS,
        "Referer": "https://cafef.vn/du-lieu/",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not data or not isinstance(data, dict):
        raise EmptyResultError(f"CafeF returned empty prices for symbols: {symbols}")

    rows: list[dict[str, Any]] = []
    for sym in symbols:
        sym_upper = sym.upper()
        item = data.get(sym_upper)
        if not item:
            continue
        # Convert CafeF units (in thousands VND) to full VND units to match Vietcap standard
        multiplier = 1000.0 if (item.get("Price") or 0) < 1000 else 1.0
        row: dict[str, Any] = {
            "listing_symbol": item.get("Symbol"),
            "listing_ref_price": (item.get("RefPrice") or 0) * multiplier,
            "listing_ceiling": (item.get("CeilingPrice") or 0) * multiplier,
            "listing_floor": (item.get("FloorPrice") or 0) * multiplier,
            "match_match_price": (item.get("Price") or 0) * multiplier,
            "match_accumulated_volume": item.get("Volume"),
            "match_high_price": (item.get("HighPrice") or 0) * multiplier,
            "match_low_price": (item.get("LowPrice") or 0) * multiplier,
            "match_foreign_buy_volume": item.get("ForeignBuyVolume"),
            "match_foreign_sell_volume": item.get("ForeignSellVolume"),
            "bid_ask_bid_1_price": (item.get("BidPrice01") or 0) * multiplier,
            "bid_ask_bid_1_volume": item.get("BidVolume01"),
            "bid_ask_bid_2_price": (item.get("BidPrice02") or 0) * multiplier,
            "bid_ask_bid_2_volume": item.get("BidVolume02"),
            "bid_ask_bid_3_price": (item.get("BidPrice03") or 0) * multiplier,
            "bid_ask_bid_3_volume": item.get("BidVolume03"),
            "bid_ask_ask_1_price": (item.get("AskPrice01") or 0) * multiplier,
            "bid_ask_ask_1_volume": item.get("AskVolume01"),
            "bid_ask_ask_2_price": (item.get("AskPrice02") or 0) * multiplier,
            "bid_ask_ask_2_volume": item.get("AskVolume02"),
            "bid_ask_ask_3_price": (item.get("AskPrice03") or 0) * multiplier,
            "bid_ask_ask_3_volume": item.get("AskVolume03"),
        }
        rows.append(row)

    if not rows:
        raise EmptyResultError(f"CafeF returned no valid items for symbols: {symbols}")

    df = pd.DataFrame(rows)
    df.columns = pd.MultiIndex.from_tuples([
        tuple(p for p in col.split("_", 1)) for col in df.columns
    ])
    df.attrs["source"] = "CAFEF_DIRECT"
    return df


def fetch_valuation_snapshot(symbol: str, timeout: int = 8) -> dict[str, Any]:
    """Fetches real-time market valuation metrics (P/E, P/B, EPS, Market Cap) from CafeF.
    Zero vnstock dependency, zero API key requirement.
    """
    url = f"https://cafef.vn/du-lieu/Ajax/PageNew/ChiSoTaiChinh.ashx?Symbol={urllib.parse.quote(symbol.upper())}"
    headers = {
        **DEFAULT_HEADERS,
        "Referer": f"https://cafef.vn/du-lieu/{symbol.lower()}.chn",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        parsed = json.loads(resp.read().decode("utf-8"))

    result: dict[str, Any] = {"symbol": symbol.upper(), "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    for item in parsed.get("Data", []):
        code = item.get("Code")
        val = item.get("Value")
        if code and val:
            result[code] = val
    return result


def fetch_raw(symbols: list[str]) -> pd.DataFrame:
    """Fetches live realtime price board.
    Zero vnstock dependency: calls Vietcap Direct REST API with automatic CafeF fallback.
    """
    try:
        return fetch_raw_vietcap(symbols)
    except Exception as e:
        logger.warning("Vietcap Direct API fetch failed (%s), falling back to CafeF...", e)
        return fetch_raw_cafef(symbols)


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Confirmed live 2026-08-14: price_board() returns a MultiIndex
    (category, field) column structure. Flatten to 'category_field'
    string keys. A no-op if columns are already flat (e.g. synthetic test
    data), so this function works for both shapes.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = pd.Index(["_".join(str(part) for part in col) for col in df.columns])
    return df


def normalize_snapshot(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: one row per symbol in the fetched price board, full
    (flattened) raw row preserved as JSON. Requires a symbol column
    (after flattening) to key rows by; fails loudly if none of
    SYMBOL_COLUMN_ALIASES is present rather than guessing. No network
    access -- fully unit-testable with synthetic DataFrames, MultiIndex
    or flat.
    """
    if raw_df.empty:
        raise EmptyResultError(
            "fetch_raw returned an empty DataFrame -- F008-compatible: "
            "recorded as genuine emptiness via record_empty(), NOT "
            "retried."
        )

    flat_df = _flatten_columns(raw_df)

    symbol_col = next((c for c in SYMBOL_COLUMN_ALIASES if c in flat_df.columns), None)
    if symbol_col is None:
        raise ValueError(
            f"Could not find a symbol column among {SYMBOL_COLUMN_ALIASES} "
            f"in fetched (flattened) price board data. Columns present: "
            f"{list(flat_df.columns)}."
        )

    # Drop rows where the symbol is missing
    flat_df = flat_df.dropna(subset=[symbol_col])
    if flat_df.empty:
        raise EmptyResultError("fetch_raw returned only empty/missing symbols.")

    snapshot_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    records = flat_df.to_dict(orient="records")

    out = pd.DataFrame(
        {
            "symbol": flat_df[symbol_col].astype(str).str.upper(),
            "snapshot_at": snapshot_at,
            "data_json": [_row_to_json(r) for r in records],
        }
    )
    out["fetched_at"] = snapshot_at

    dupes = out.duplicated(subset=["symbol", "snapshot_at"]).sum()
    if dupes:
        raise ValueError(
            f"normalize_snapshot produced {dupes} duplicate (symbol, "
            f"snapshot_at) row(s) -- refusing to write ambiguous data."
        )

    return out[SNAPSHOT_COLUMNS]


def _row_to_json(row: dict[object, object]) -> str:
    def _default(o: object) -> str:
        return str(o)

    return json.dumps(row, default=_default, ensure_ascii=False)


def write_snapshot(df: pd.DataFrame, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Validate + write to staging, then promote to core. ACCUMULATE
    retention (DECISIONS.md 2026-08-14): never deletes prior snapshots for
    a symbol -- only guards against re-inserting the exact same
    (symbol, snapshot_at) key.
    """
    missing = set(SNAPSHOT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Snapshot DataFrame missing columns: {missing}")

    should_close = False
    if con is None:
        con = db.bootstrap_schema()
        should_close = True

    try:
        con.register("snapshot_df", df[SNAPSHOT_COLUMNS])
        con.execute(
            "INSERT INTO staging.realtime_quote_snapshot SELECT * FROM snapshot_df "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM staging.realtime_quote_snapshot s "
            "  WHERE s.symbol = snapshot_df.symbol AND s.snapshot_at = snapshot_df.snapshot_at"
            ")"
        )
        con.execute(
            "INSERT INTO core.realtime_quote_snapshot SELECT * FROM snapshot_df "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM core.realtime_quote_snapshot s "
            "  WHERE s.symbol = snapshot_df.symbol AND s.snapshot_at = snapshot_df.snapshot_at"
            ")"
        )
        con.unregister("snapshot_df")
    finally:
        if should_close:
            con.close()

    return len(df)


def run(symbols: list[str] | str, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Entry point: fetch live, normalize, write. Returns row count written.

    Accepts either a single symbol (str) or a list of symbols for a
    genuine multi-symbol price-board snapshot in one call.
    """
    if isinstance(symbols, str):
        symbols = [symbols]
    raw = fetch_raw(symbols)
    normalized = normalize_snapshot(raw)
    return write_snapshot(normalized, con=con)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F007: crawl a realtime price-board snapshot via Direct REST API")
    parser.add_argument("symbols", nargs="+", help="One or more ticker symbols")
    args = parser.parse_args()

    n = run(args.symbols)
    print(f"F007 realtime_quote_snapshot: wrote {n} rows to core.realtime_quote_snapshot")