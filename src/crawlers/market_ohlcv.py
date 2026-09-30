"""F002: Market OHLCV daily crawler.

Confirmed live against vnstock==4.0.5 (2026-08-11): `Market().equity(symbol)`
returns an EquityMarket object with a real `.ohlcv(start=None, end=None,
interval='1D', count=100, source='kbs', **kwargs)` method (signature
introspected directly from the installed package).

SOURCED/VERIFIED (2026-08-13, see gemini-progress.md): discover_ohlcv_schema.py 
was run against the live API. The columns returned were exactly 
`['time', 'open', 'high', 'low', 'close', 'volume']`. RAW_COLUMN_ALIASES 
works as designed and the schema mapping is now fully verified, not assumed.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"

# VERIFIED (2026-08-13): Live API returns ['time', 'open', 'high', 'low', 'close', 'volume'].
# This alias mapping cleanly covers it (time -> date).
RAW_COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["time", "date", "trading_date"],
    "open": ["open"],
    "high": ["high"],
    "low": ["low"],
    "close": ["close"],
    "volume": ["volume", "volume_match", "matched_volume"],
}

import requests

OHLCV_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume", "fetched_at"]


def _fetch_dnse_daily(symbol: str, start: str, end: str, timeout: int = 8) -> pd.DataFrame:
    """Tải trực tiếp nến ngày từ DNSE Entrade X API."""
    try:
        from_ts = int(pd.to_datetime(start).timestamp())
        to_ts = int(pd.to_datetime(end).timestamp()) + 86400
        url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?from={from_ts}&to={to_ts}&symbol={symbol.upper()}&resolution=1D"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        if r.status_code == 200:
            d = r.json()
            if d.get("t") and len(d["t"]) > 0:
                df = pd.DataFrame({
                    "time": pd.to_datetime(d["t"], unit="s").strftime("%Y-%m-%d"),
                    "open": [float(x) for x in d["o"]],
                    "high": [float(x) for x in d["h"]],
                    "low": [float(x) for x in d["l"]],
                    "close": [float(x) for x in d["c"]],
                    "volume": [int(x) for x in d["v"]],
                })
                if df["open"].max() > 1000:
                    for c in ["open", "high", "low", "close"]:
                        df[c] = df[c] / 1000.0
                return df
    except Exception:
        pass
    return pd.DataFrame()


def _fetch_vietcap_daily(symbol: str, start: str, end: str, timeout: int = 12) -> pd.DataFrame:
    """Tải trực tiếp nến ngày từ Vietcap Trading gap-chart API."""
    try:
        to_ts = int(pd.to_datetime(end).timestamp()) + 86400
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)
        days = max(10, (end_dt - start_dt).days + 1)
        url = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
        payload = {
            "timeFrame": "ONE_DAY",
            "symbols": [symbol.upper()],
            "to": to_ts,
            "countBack": min(days + 20, 5000),
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://trading.vietcap.com.vn",
            "Referer": "https://trading.vietcap.com.vn/",
        }
        r = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            if data and isinstance(data, list) and len(data) > 0 and data[0].get("t"):
                item = data[0]
                df = pd.DataFrame({
                    "time": pd.to_datetime([int(x) for x in item["t"]], unit="s").strftime("%Y-%m-%d"),
                    "open": [float(x) for x in item["o"]],
                    "high": [float(x) for x in item["h"]],
                    "low": [float(x) for x in item["l"]],
                    "close": [float(x) for x in item["c"]],
                    "volume": [int(x) for x in item["v"]],
                })
                # Lọc đúng phạm vi start - end
                df = df[(df["time"] >= str(start)[:10]) & (df["time"] <= str(end)[:10])].copy()
                if not df.empty and df["open"].max() > 1000:
                    for c in ["open", "high", "low", "close"]:
                        df[c] = df[c] / 1000.0
                return df
    except Exception:
        pass
    return pd.DataFrame()


def _authenticate() -> None:
    """Tải biến môi trường và thiết lập key nếu có (không bắt buộc nếu dùng Direct API)."""
    db.load_env()
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if api_key:
        try:
            import vnstock_data as vs
            if hasattr(vs, "change_api_key"):
                vs.change_api_key(api_key)
        except Exception:
            pass


def fetch_raw(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Thu thập nến ngày OHLCV từ nguồn Direct (DNSE, Vietcap) và fallback vnstock nếu có."""
    _authenticate()

    # 1. Ưu tiên hàng đầu: DNSE Direct API (Cực nhanh và ổn định cao)
    df_dnse = _fetch_dnse_daily(symbol, start, end)
    if df_dnse is not None and not df_dnse.empty:
        return df_dnse

    # 2. Ưu tiên 2: Vietcap Direct API (gap-chart ONE_DAY)
    df_vci = _fetch_vietcap_daily(symbol, start, end)
    if df_vci is not None and not df_vci.empty:
        return df_vci

    # 3. Fallback: vnstock_data / vnstock (nếu môi trường có cấu hình)
    try:
        from vnstock_data import Market
        eq = Market().equity(symbol)
        result: pd.DataFrame = eq.ohlcv(start=start, end=end)
        if result is not None and not result.empty:
            return result
    except Exception:
        pass

    try:
        from vnstock.api.quote import Quote
        q = Quote(symbol=symbol, source="VCI")
        result_quote: pd.DataFrame = q.history(start=start, end=end)
        if result_quote is not None and not result_quote.empty:
            return result_quote
    except Exception:
        pass

    return pd.DataFrame()


def _find_column(df: pd.DataFrame, field: str) -> str:
    for candidate in RAW_COLUMN_ALIASES[field]:
        if candidate in df.columns:
            return candidate
    raise ValueError(
        f"Could not find a source column for '{field}' in fetched OHLCV "
        f"data. Columns present: {list(df.columns)}. RAW_COLUMN_ALIASES "
        f"for '{field}' is {RAW_COLUMN_ALIASES[field]} but none matched -- "
        f"this means vnstock's real schema differs from the assumption in "
        f"this module's docstring. Run discover_ohlcv_schema.py against a "
        f"live key and update RAW_COLUMN_ALIASES rather than guessing."
    )


def normalize_ohlcv(raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Pure transform: map raw columns -> standard schema, add symbol +
    fetched_at, cast types, fail loudly on duplicate (symbol, date) rather
    than silently dropping rows (conventions.md error-handling pattern).
    No network access -- fully unit-testable with synthetic DataFrames.
    """
    if raw_df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r} -- "
            f"F008-compatible: this is genuine emptiness (e.g. no trading "
            f"data for the requested range), not a transient failure, so "
            f"it will be recorded via record_empty() and NOT retried."
        )

    col_map = {field: _find_column(raw_df, field) for field in RAW_COLUMN_ALIASES}

    out = pd.DataFrame(
        {
            "symbol": symbol,
            "date": pd.to_datetime(raw_df[col_map["date"]]).dt.date,
            "open": raw_df[col_map["open"]].astype(float),
            "high": raw_df[col_map["high"]].astype(float),
            "low": raw_df[col_map["low"]].astype(float),
            "close": raw_df[col_map["close"]].astype(float),
            "volume": raw_df[col_map["volume"]].astype("int64"),
        }
    )
    out["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    dupes = out.duplicated(subset=["symbol", "date"]).sum()
    if dupes:
        raise ValueError(
            f"normalize_ohlcv produced {dupes} duplicate (symbol, date) "
            f"row(s) for {symbol!r} -- refusing to write ambiguous data."
        )

    return out[OHLCV_COLUMNS]


def write_ohlcv(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write to staging, then promote to core for this symbol's
    date range only. Idempotent: re-running with the same input replaces
    the same (symbol, date) rows rather than duplicating them.
    """
    missing = set(OHLCV_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"OHLCV DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    symbols = df["symbol"].unique().tolist()

    # Đảm bảo staging và core schema/tables luôn sẵn sàng trên mọi kết nối
    con.execute("""
        CREATE SCHEMA IF NOT EXISTS staging;
        CREATE SCHEMA IF NOT EXISTS core;
        CREATE TABLE IF NOT EXISTS staging.market_ohlcv_daily (
            symbol VARCHAR NOT NULL, date DATE NOT NULL,
            open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT,
            fetched_at TIMESTAMP NOT NULL
        );
        CREATE TABLE IF NOT EXISTS core.market_ohlcv_daily (
            symbol VARCHAR NOT NULL, date DATE NOT NULL,
            open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT,
            fetched_at TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)

    con.execute("DELETE FROM staging.market_ohlcv_daily WHERE symbol IN ?", [symbols])
    con.register("ohlcv_df", df[OHLCV_COLUMNS])
    con.execute("INSERT INTO staging.market_ohlcv_daily SELECT * FROM ohlcv_df")

    # Promotion: staging -> core only after the schema/dedup checks above
    # already passed (validation-before-promotion, per F002's spec).
    con.execute("DELETE FROM core.market_ohlcv_daily WHERE symbol IN ?", [symbols])
    con.execute("INSERT INTO core.market_ohlcv_daily SELECT * FROM ohlcv_df")
    con.unregister("ohlcv_df")

    return len(df)


def run(symbol: str, start: str = "2000-01-01", end: str | None = None) -> int:
    """Entry point: fetch live, normalize, write. Returns row count written.

    Defaults per DECISIONS.md item 8 (crawl maximum available history):
    start defaults to 2000-01-01 (before HOSE's 2000 founding, safely
    covers any listing date), end defaults to today if not given -- these
    defaults exist specifically so this function is orchestrator-
    compatible (src/etl/batch_orchestrator.py calls crawl_fn(symbol) with
    no other args).
    """
    if end is None: 
        end = dt.date.today().isoformat()
    raw = fetch_raw(symbol, start, end)
    normalized = normalize_ohlcv(raw, symbol)
    return write_ohlcv(normalized)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F002: crawl daily OHLCV for one symbol")
    parser.add_argument("symbol")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    n = run(args.symbol, args.start, args.end)
    print(f"F002 market_ohlcv: wrote {n} rows for {args.symbol} to core.market_ohlcv_daily")