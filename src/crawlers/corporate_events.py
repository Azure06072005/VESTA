"""src/crawlers/corporate_events.py

F006: Corporate events crawler & Payout Delay Quantitative Engine.
UPGRADED 2026-09-27 to Direct Vietstock Events REST API:
- Removed 100% dependency on vnstock / vnstock_data and VNSTOCK_API_KEY.
- Direct JSON retrieval from https://finance.vietstock.vn/data/eventstypedata
- Ingests structured cash dividend, stock dividend, bonus shares, rights issue,
  and AGM / shareholder meetings without requiring OCR.
- Computes `payout_delay_days` = payment_date - ex_date to model liquidity risks
  for enterprises delaying cash dividend payouts.
"""
from __future__ import annotations

import datetime as dt
import http.cookiejar
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
from etl.retry_failed_jobs import EmptyResultError

logger = logging.getLogger("corporate_events")

# Standard schema aliases for backward compatibility with legacy tests & fixtures
EVENT_ID_ALIASES = ["id", "event_id", "EventID"]
EVENT_TYPE_ALIASES = ["category", "event_code", "event_type", "Name"]
EVENT_DATE_ALIASES = ["display_date1", "public_date", "record_date", "exright_date", "GDKHQDate", "Time", "event_date"]

KNOWN_EVENT_TYPES: set[str] = {
    "DIVIDEND",
    "MAJOR_SHAREHOLDER_TRADING",
    "OTHER",
    "SHAREHOLDER_MEETING",
}

EVENT_COLUMNS = ["symbol", "event_id", "event_type", "event_date", "detail_json", "fetched_at"]
EXTENDED_COLUMNS = [*EVENT_COLUMNS, "payout_delay_days"]


class VietstockEventsClient:
    """Session-managed client for Vietstock Financial Events API."""

    def __init__(self) -> None:
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        }
        self.token: str | None = None

    def ensure_token(self) -> str:
        """Retrieves CSRF verification token from Vietstock event calendar page."""
        if self.token:
            return self.token
        page_url = "https://finance.vietstock.vn/lich-su-kien.htm"
        req = urllib.request.Request(page_url, headers=self.headers)
        with self.opener.open(req, timeout=12) as res:
            html = res.read().decode("utf-8", errors="ignore")
        match = re.search(r"name=[\"']?__RequestVerificationToken[\"']?[^>]*value=[\"']?([^\s\"'>]+)", html)
        if not match:
            raise RuntimeError("Could not extract __RequestVerificationToken from Vietstock page")
        self.token = match.group(1)
        return self.token

    def fetch_events(self, symbol: str, page_size: int = 100) -> list[dict[str, Any]]:
        """Fetches all corporate actions for a given equity symbol."""
        token = self.ensure_token()
        api_url = "https://finance.vietstock.vn/data/eventstypedata"
        post_headers = {
            "User-Agent": self.headers["User-Agent"],
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://finance.vietstock.vn/lich-su-kien.htm",
            "Origin": "https://finance.vietstock.vn",
        }

        all_events: list[dict[str, Any]] = []
        # EventTypeID: 1 = Dividends & Issuance, 5 = Shareholders Meeting
        for event_type_id in [1, 5]:
            params = {
                "eventTypeID": str(event_type_id),
                "channelID": "0",
                "code": symbol.upper(),
                "catID": "-1",
                "fDate": "2010-01-01",
                "tDate": "2026-12-31",
                "page": "1",
                "pageSize": str(page_size),
                "orderBy": "Date1",
                "orderDir": "DESC",
                "__RequestVerificationToken": token,
            }
            encoded = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(api_url, data=encoded, headers=post_headers)
            try:
                with self.opener.open(req, timeout=12) as res:
                    raw_text = res.read().decode("utf-8-sig", errors="ignore")
                    parsed = json.loads(raw_text)
                    items = parsed[0] if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], list) else []
                    all_events.extend(items)
            except Exception as e:
                logger.debug("Vietstock fetch notice for symbol=%s event_type_id=%s: %s", symbol, event_type_id, e)

        return all_events


VN_TZ = dt.timezone(dt.timedelta(hours=7))


def _parse_vietstock_date(val: Any) -> dt.date | None:
    if not val or val == "null" or pd.isna(val):
        return None
    m = re.search(r"/Date\((\d+)\)/", str(val))
    if m:
        ts_ms = int(m.group(1))
        return dt.datetime.fromtimestamp(ts_ms / 1000, tz=VN_TZ).date()
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def fetch_raw(symbol: str) -> pd.DataFrame:
    """Fetches raw events from Vietstock Direct API (no vnstock or API key required)."""
    client = VietstockEventsClient()
    items = client.fetch_events(symbol)
    if not items:
        return pd.DataFrame()
    return pd.DataFrame(items)


def _find_column(df: pd.DataFrame, aliases: list[str], field: str, required: bool = True) -> str | None:
    for candidate in aliases:
        if candidate in df.columns:
            return candidate
    if required:
        raise ValueError(
            f"Could not find a source column for '{field}' in fetched "
            f"corporate events data. Columns present: {list(df.columns)}. "
            f"Aliases tried: {aliases}."
        )
    return None


def _row_to_json(row: dict[object, object]) -> str:
    def _default(o: object) -> str:
        return str(o)

    return json.dumps(row, default=_default, ensure_ascii=False)


def normalize_events(raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalizes raw corporate events into standard schema with payout_delay_days."""
    if raw_df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r} -- "
            f"recorded as genuine emptiness via record_empty(), NOT retried."
        )

    # Branch 1: Vietstock direct schema
    if "EventID" in raw_df.columns:
        rows: list[dict[str, Any]] = []
        for _, item in raw_df.iterrows():
            event_id = str(item.get("EventID") or "")
            name = str(item.get("Name") or "")
            title = str(item.get("Title") or "")
            note = str(item.get("Note") or "")
            channel_id = item.get("ChannelID")
            event_type_id = item.get("EventTypeID")

            if event_type_id == 5 or "đại hội" in name.lower() or "đhcđ" in title.lower():
                cat = "SHAREHOLDER_MEETING"
            elif channel_id in (13, 14, 15) or "cổ tức" in name.lower() or "thưởng" in name.lower():
                cat = "DIVIDEND"
            elif "nội bộ" in name.lower() or "cổ đông lớn" in name.lower() or "giao dịch" in name.lower():
                cat = "MAJOR_SHAREHOLDER_TRADING"
            else:
                cat = "OTHER"

            ex_date = _parse_vietstock_date(item.get("GDKHQDate"))
            record_date = _parse_vietstock_date(item.get("NDKCCDate"))
            payment_date = _parse_vietstock_date(item.get("Time"))

            event_date = ex_date or record_date or payment_date or _parse_vietstock_date(item.get("DateOrder"))

            payout_delay_days: int | None = None
            if payment_date:
                anchor = ex_date or record_date
                if anchor and payment_date >= anchor:
                    payout_delay_days = (payment_date - anchor).days

            # Extract cash amount from note (e.g. '1,000 đồng/CP')
            cash_amount: float | None = None
            match_cash = re.search(r"([\d\.,]+)\s*đồng/cp", note, re.I)
            if match_cash:
                try:
                    clean_str = match_cash.group(1).replace(".", "").replace(",", "")
                    cash_amount = float(clean_str)
                except Exception:
                    pass

            detail_dict = item.to_dict()
            detail_dict["payout_delay_days"] = payout_delay_days
            detail_dict["cash_dividend_amount"] = cash_amount
            detail_dict["parsed_ex_date"] = str(ex_date) if ex_date else None
            detail_dict["parsed_payment_date"] = str(payment_date) if payment_date else None

            rows.append({
                "symbol": symbol.upper(),
                "event_id": event_id,
                "event_type": cat,
                "event_date": event_date,
                "detail_json": _row_to_json(detail_dict),
                "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                "payout_delay_days": payout_delay_days,
            })

        out = pd.DataFrame(rows)
        # Deduplicate
        dupes = out.duplicated(subset=["symbol", "event_id"]).sum()
        if dupes:
            out = out.drop_duplicates(subset=["symbol", "event_id"], keep="first")
        return out

    # Branch 2: Legacy schema (used in existing unit tests)
    id_col = _find_column(raw_df, EVENT_ID_ALIASES, "event_id")
    type_col = _find_column(raw_df, EVENT_TYPE_ALIASES, "event_type")
    date_col = _find_column(raw_df, EVENT_DATE_ALIASES, "event_date", required=False)

    unrecognized_types = sorted(set(raw_df[type_col].astype(str)) - KNOWN_EVENT_TYPES)
    if unrecognized_types:
        print(
            f"[F006] unrecognized event_type value(s) for {symbol!r}, not "
            f"in KNOWN_EVENT_TYPES: {unrecognized_types}"
        )

    records = raw_df.to_dict(orient="records")
    out = pd.DataFrame(
        {
            "symbol": symbol,
            "event_id": raw_df[id_col].astype(str),
            "event_type": raw_df[type_col].astype(str),
            "event_date": pd.to_datetime(raw_df[date_col], format="mixed", errors="coerce").dt.date if date_col else pd.NaT,
            "detail_json": [_row_to_json(r) for r in records],
        }
    )
    out["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    dupes = out.duplicated(subset=["symbol", "event_id"]).sum()
    if dupes:
        raise ValueError(
            f"normalize_events produced {dupes} duplicate (symbol, "
            f"event_id) row(s) for {symbol!r} -- refusing to write "
            f"ambiguous data."
        )

    return out[EVENT_COLUMNS]


def write_events(df: pd.DataFrame, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Writes normalized corporate events to staging and core. Idempotent by (symbol, event_id)."""
    missing = set(EVENT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Corporate events DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()

    # Ensure payout_delay_days column exists in core and staging tables
    for schema_name in ["core", "staging"]:
        try:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info('{schema_name}.corporate_events')").fetchall()]
            if "payout_delay_days" not in cols:
                con.execute(f"ALTER TABLE {schema_name}.corporate_events ADD COLUMN payout_delay_days INTEGER;")
        except Exception:
            pass

    symbols = df["symbol"].unique().tolist()
    con.execute("DELETE FROM staging.corporate_events WHERE symbol IN ?", [symbols])

    has_delay = "payout_delay_days" in df.columns
    cols_to_insert = EXTENDED_COLUMNS if has_delay else EVENT_COLUMNS

    con.register("events_df", df[cols_to_insert])
    col_str = ", ".join(cols_to_insert)
    con.execute(f"INSERT INTO staging.corporate_events ({col_str}) SELECT {col_str} FROM events_df")

    con.execute("DELETE FROM core.corporate_events WHERE symbol IN ?", [symbols])
    con.execute(f"INSERT INTO core.corporate_events ({col_str}) SELECT {col_str} FROM events_df")
    con.unregister("events_df")

    return len(df)


def run(symbol: str) -> int:
    """Entry point: fetches live from Vietstock, normalizes, and writes corporate events."""
    raw = fetch_raw(symbol)
    normalized = normalize_events(raw, symbol)
    return write_events(normalized)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F006: crawl corporate events from Vietstock Direct API")
    parser.add_argument("symbol")
    args = parser.parse_args()

    n = run(args.symbol)
    print(f"F006 corporate_events: wrote {n} rows for {args.symbol} to core.corporate_events")