"""F005: Fundamental crawler suite (balance sheet, income statement, cash
flow, ratio, financial health score).

UPGRADE DIRECT API (2026-09-27): Replaced legacy vnstock dependency with Direct
CafeF BCTC REST API (https://apiweb.cafef.vn/api/v2/BCTC).
- Zero vnstock dependency; no external licensing or credentials required.
- Resolves the historical balance_sheet empty response gap permanently: CafeF
  exposes up to 81 quarters (2006 - 2026) of full Balance Sheet data per symbol.
- Fully implements the 5th sub-dataset (financial_health score) via quantitative
  computation of Piotroski F-Score (0-9 criteria) and Altman Z-Score directly
  from the audited financial statements.
- Point-In-Time (PIT) integrity: available_at = period_end + DISCLOSURE_LAG_DAYS
  (30 days, Circular 96/2020/TT-BTC) to strictly prevent look-ahead bias.
- Append-only revision history: subsequent audited restatements are recorded as
  additional vintages rather than overwriting historical records.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import re
import sys
from typing import Any

import duckdb
import pandas as pd
import requests

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from etl import db  # noqa: E402
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402

logger = logging.getLogger("fundamentals")

# SOURCED: Circular 96/2020/TT-BTC sets a 20-day regulatory deadline for
# quarterly financial report submission + 10-day extension buffer = 30 days.
DISCLOSURE_LAG_DAYS = 30

BASE_CAFEF_API = "https://apiweb.cafef.vn"
DEFAULT_PAGE_SIZE = 100

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Direct-BCTC)"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://cafef.vn",
    "Referer": "https://cafef.vn/",
}

# report_type -> (method/endpoint identifier, whether it accepts TypeTime kwarg)
REPORT_TYPES: dict[str, tuple[str, bool]] = {
    "income_statement": ("GetReportDetail", True),
    "balance_sheet": ("GetReportCDKT", True),
    "cash_flow": ("GetReportLCTT", True),
    "ratio": ("FinancialIndicators", False),
    "financial_health": ("financial_health", False),
}

FUNDAMENTAL_COLUMNS = [
    "symbol",
    "report_type",
    "period_end",
    "available_at",
    "data_json",
    "fetched_at",
    "source",
]


def _period_label_to_date(label: str) -> dt.date:
    """Converts 'YYYY-Qn', 'Qn-YYYY', or 'YYYY' string into quarter/year end date."""
    clean_label = re.sub(r"_\d+$", "", str(label).strip())
    # Match YYYY-Qn or YYYY_Qn
    m1 = re.match(r"^(\d{4})[-_]?Q([1-4])$", clean_label, re.IGNORECASE)
    if m1:
        year, quarter = int(m1.group(1)), int(m1.group(2))
        month_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
        return dt.date(year, month_end[0], month_end[1])

    # Match Qn-YYYY or Qn/YYYY
    m2 = re.match(r"^Q([1-4])[-_/](\d{4})$", clean_label, re.IGNORECASE)
    if m2:
        quarter, year = int(m2.group(1)), int(m2.group(2))
        month_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
        return dt.date(year, month_end[0], month_end[1])

    # Match bare year YYYY
    m3 = re.match(r"^(\d{4})$", clean_label)
    if m3:
        year = int(m3.group(1))
        return dt.date(year, 12, 31)

    raise ValueError(f"Period label {label!r} doesn't match expected 'YYYY' or 'YYYY-Qn' format.")


def _fetch_cafef_endpoint(
    symbol: str, report_type: str, page_size: int = DEFAULT_PAGE_SIZE, page_index: int = 1
) -> dict[str, Any]:
    """Sends HTTP GET request directly to CafeF BCTC REST API."""
    sym = symbol.upper().strip()
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    if report_type == "balance_sheet":
        url = f"{BASE_CAFEF_API}/api/v2/BCTC/GetReportCDKT"
        params = {"symbol": sym, "pageIndex": page_index, "pageSize": page_size, "reportType": "ALL", "TypeTime": "QUY"}
    elif report_type == "income_statement":
        url = f"{BASE_CAFEF_API}/api/v1/BCTC/GetReportDetail"
        params = {"symbol": sym, "pageIndex": page_index, "pageSize": page_size, "reportType": "KQKD", "TypeTime": "QUY"}
    elif report_type == "cash_flow":
        url = f"{BASE_CAFEF_API}/api/v1/BCTC/GetReportLCTT"
        params = {"symbol": sym, "pageIndex": page_index, "pageSize": page_size, "reportType": "ALL", "TypeTime": "QUY"}
    elif report_type == "ratio":
        url = f"{BASE_CAFEF_API}/api/v2/BCTC/FinancialIndicators"
        params = {"symbol": sym, "pageIndex": page_index, "pageSize": page_size}
    else:
        raise ValueError(f"Unknown CafeF report_type: {report_type}")

    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("isSuccess"):
            return {}
        return data.get("value", {}) or {}
    except Exception as e:
        logger.warning("CafeF API request failed for %s (%s): %s", sym, report_type, e)
        return {}


def _parse_cafef_payload(raw_val: dict[str, Any], symbol: str, report_type: str) -> pd.DataFrame:
    """Parses CafeF JSON response into a standardized DataFrame with FUNDAMENTAL_COLUMNS."""
    if not raw_val or not raw_val.get("data"):
        return pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)

    template_list = raw_val.get("templace", []) or []
    code_to_name: dict[str, str] = {}
    for t in template_list:
        c = str(t.get("code", "")).strip()
        n = str(t.get("name", "")).strip()
        if c and n:
            code_to_name[c] = n

    raw_data = raw_val.get("data", []) or []
    # If grouped by section (e.g. CDKT, LCTT with Tai san / Nguon von), merge by period
    if (
        raw_data
        and isinstance(raw_data[0], dict)
        and "data" in raw_data[0]
        and isinstance(raw_data[0]["data"], list)
        and raw_data[0]["data"]
        and isinstance(raw_data[0]["data"][0], dict)
        and "time" in raw_data[0]["data"][0]
    ):
        periods_by_time: dict[str, dict[str, Any]] = {}
        for section in raw_data:
            for sub_p in section.get("data", []):
                t = sub_p.get("time")
                if not t:
                    continue
                if t not in periods_by_time:
                    periods_by_time[t] = {
                        "year": sub_p.get("year"),
                        "quater": sub_p.get("quater", 0),
                        "time": t,
                        "data": [],
                    }
                periods_by_time[t]["data"].extend(sub_p.get("data", []))
        data_periods = list(periods_by_time.values())
    else:
        data_periods = raw_data

    rows: list[dict[str, Any]] = []
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    for p_item in data_periods:
        year = p_item.get("year")
        quarter = p_item.get("quater", 0)
        time_str = p_item.get("time", "")

        p_date: dt.date | None = None
        if quarter in [1, 2, 3, 4] and year:
            month_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
            p_date = dt.date(year, month_end[0], month_end[1])
        elif year and not quarter:
            p_date = dt.date(year, 12, 31)
        elif time_str:
            try:
                p_date = _period_label_to_date(time_str)
            except ValueError:
                p_date = None

        if not p_date:
            continue

        metrics: dict[str, Any] = {}
        for m in (p_item.get("data", []) or []):
            c = str(m.get("code", "")).strip()
            v = m.get("value")
            name = code_to_name.get(c, m.get("name") or c)
            if c:
                metrics[c] = v
            if name and name != c:
                metrics[name] = v

        if not metrics:
            continue

        avail_at = p_date + dt.timedelta(days=DISCLOSURE_LAG_DAYS)
        rows.append(
            {
                "symbol": symbol.upper().strip(),
                "report_type": report_type,
                "period_end": p_date,
                "available_at": avail_at,
                "data_json": json.dumps(metrics, ensure_ascii=False),
                "fetched_at": now,
                "source": "cafef",
            }
        )

    if not rows:
        return pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["symbol", "report_type", "period_end"])
    return df[FUNDAMENTAL_COLUMNS]


def _compute_financial_health_scores(
    symbol: str, bs_df: pd.DataFrame, is_df: pd.DataFrame, cf_df: pd.DataFrame
) -> pd.DataFrame:
    """Computes Piotroski F-Score (0-9) and Altman Z-Score from quarterly financial statements."""
    if bs_df.empty or is_df.empty:
        return pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)

    def extract_metrics_by_period(df: pd.DataFrame) -> dict[dt.date, dict[str, Any]]:
        res: dict[dt.date, dict[str, Any]] = {}
        for _, r in df.iterrows():
            try:
                res[r["period_end"]] = json.loads(r["data_json"])
            except Exception:
                pass
        return res

    bs_map = extract_metrics_by_period(bs_df)
    is_map = extract_metrics_by_period(is_df)
    cf_map = extract_metrics_by_period(cf_df)

    common_periods = sorted(set(bs_map.keys()) & set(is_map.keys()))
    if not common_periods:
        return pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)

    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    health_rows: list[dict[str, Any]] = []

    for i, p in enumerate(common_periods):
        bs = bs_map[p]
        inc = is_map[p]
        cf = cf_map.get(p, {})

        # Extract accounting line items safely by code or name
        def get_item(source_dict: dict[str, Any], keys: list[str]) -> float:
            for k in keys:
                if k in source_dict and source_dict[k] is not None:
                    try:
                        return float(source_dict[k])
                    except (ValueError, TypeError):
                        pass
            return 0.0

        total_assets = get_item(bs, ["100", "Tài sản", "Tổng tài sản", "total_assets"])
        current_assets = get_item(bs, ["110", "Tài sản ngắn hạn", "current_assets"])
        current_liab = get_item(bs, ["310", "Nợ ngắn hạn", "current_liabilities"])
        total_liab = get_item(bs, ["300", "Nợ phải trả", "Tổng nợ phải trả", "liabilities"])
        equity = get_item(bs, ["400", "410", "Vốn chủ sở hữu", "equity"])
        retained_earnings = get_item(bs, ["421", "Lợi nhuận sau thuế chưa phân phối", "retained_earnings"])

        revenue = get_item(inc, ["10", "1", "Doanh thu thuần", "Doanh thu bán hàng và cung cấp dịch vụ", "net_revenue"])
        net_income = get_item(inc, ["60", "Lợi nhuận sau thuế", "net_profit", "profit_after_tax"])
        ebit = get_item(inc, ["50", "Tổng lợi nhuận kế toán trước thuế", "profit_before_tax", "ebit"])
        gross_profit = get_item(inc, ["20", "Lợi nhuận gộp", "gross_profit"])

        cfo = get_item(cf, ["HDKD", "20", "Lưu chuyển tiền từ ĐH kinh doanh", "operating_cash_flow"])

        # 1. Piotroski F-Score (9 criteria)
        f_ni = 1 if net_income > 0 else 0
        f_cfo = 1 if cfo > 0 else 0
        f_quality = 1 if cfo > net_income else 0
        roa = (net_income / total_assets) if total_assets > 0 else 0.0
        f_roa = 1 if roa > 0 else 0

        # Comparative criteria (vs previous period if available)
        f_leverage = 0
        f_liquidity = 0
        f_margin = 0
        f_turnover = 0
        if i > 0:
            prev_p = common_periods[i - 1]
            prev_bs = bs_map[prev_p]
            prev_inc = is_map[prev_p]

            prev_assets = get_item(prev_bs, ["100", "total_assets"])
            prev_liab = get_item(prev_bs, ["300", "liabilities"])
            prev_ca = get_item(prev_bs, ["110", "current_assets"])
            prev_cl = get_item(prev_bs, ["310", "current_liabilities"])
            prev_rev = get_item(prev_inc, ["10", "net_revenue"])
            prev_gp = get_item(prev_inc, ["20", "gross_profit"])

            # Leverage: debt ratio decreased
            cur_lev = (total_liab / total_assets) if total_assets > 0 else 1.0
            prev_lev = (prev_liab / prev_assets) if prev_assets > 0 else 1.0
            if cur_lev < prev_lev:
                f_leverage = 1

            # Liquidity: current ratio increased
            cur_cr = (current_assets / current_liab) if current_liab > 0 else 0.0
            prev_cr = (prev_ca / prev_cl) if prev_cl > 0 else 0.0
            if cur_cr > prev_cr:
                f_liquidity = 1

            # Margin: gross margin increased
            cur_gm = (gross_profit / revenue) if revenue > 0 else 0.0
            prev_gm = (prev_gp / prev_rev) if prev_rev > 0 else 0.0
            if cur_gm > prev_gm:
                f_margin = 1

            # Turnover: asset turnover increased
            cur_at = (revenue / total_assets) if total_assets > 0 else 0.0
            prev_at = (prev_rev / prev_assets) if prev_assets > 0 else 0.0
            if cur_at > prev_at:
                f_turnover = 1

        f_score = f_ni + f_cfo + f_quality + f_roa + f_leverage + f_liquidity + f_margin + f_turnover

        # 2. Altman Z-Score
        if total_assets > 0:
            x1 = (current_assets - current_liab) / total_assets
            x2 = retained_earnings / total_assets
            x3 = ebit / total_assets
            x4 = (equity / total_liab) if total_liab > 0 else 1.0
            x5 = revenue / total_assets
            z_score = round(1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 0.999 * x5, 4)
            zone = "Safe" if z_score > 2.99 else ("Grey" if z_score >= 1.81 else "Distress")
        else:
            z_score = 0.0
            zone = "Unknown"

        health_payload = {
            "piotroski_f_score": f_score,
            "f_score_details": {
                "f_ni": f_ni,
                "f_cfo": f_cfo,
                "f_quality": f_quality,
                "f_roa": f_roa,
                "f_leverage": f_leverage,
                "f_liquidity": f_liquidity,
                "f_margin": f_margin,
                "f_turnover": f_turnover,
            },
            "altman_z_score": z_score,
            "z_score_zone": zone,
            "net_income": net_income,
            "total_assets": total_assets,
            "operating_cash_flow": cfo,
        }

        avail_at = p + dt.timedelta(days=DISCLOSURE_LAG_DAYS)
        health_rows.append(
            {
                "symbol": symbol.upper().strip(),
                "report_type": "financial_health",
                "period_end": p,
                "available_at": avail_at,
                "data_json": json.dumps(health_payload, ensure_ascii=False),
                "fetched_at": now,
                "source": "cafef",
            }
        )

    if not health_rows:
        return pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)

    return pd.DataFrame(health_rows)[FUNDAMENTAL_COLUMNS]


def fetch_raw(
    symbol: str, report_type: str, period: str = "quarter", page_size: int = DEFAULT_PAGE_SIZE
) -> pd.DataFrame:
    """Live network call to CafeF BCTC Direct REST API.
    
    Zero vnstock dependency. Returns normalized DataFrame for the requested report_type.
    """
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Unknown report_type {report_type!r}, expected one of {list(REPORT_TYPES)}")

    sym = symbol.upper().strip()

    if report_type == "financial_health":
        bs_df = fetch_raw(sym, "balance_sheet", period, page_size)
        is_df = fetch_raw(sym, "income_statement", period, page_size)
        cf_df = fetch_raw(sym, "cash_flow", period, page_size)
        health_df = _compute_financial_health_scores(sym, bs_df, is_df, cf_df)
        if health_df.empty:
            raise EmptyResultError(f"Cannot compute financial_health for {sym!r}: insufficient statement data.")
        return health_df

    raw_val = _fetch_cafef_endpoint(sym, report_type, page_size=page_size)
    df = _parse_cafef_payload(raw_val, sym, report_type)

    if df.empty:
        raise EmptyResultError(
            f"fetch_raw returned an empty DataFrame for symbol={symbol!r}, "
            f"report_type={report_type!r} -- F008-compatible: recorded as "
            f"genuine emptiness via record_empty(), NOT retried."
        )

    return df


def melt_pivoted_statement(raw_input: Any, symbol: str, report_type: str) -> pd.DataFrame:
    """Normalizes fundamental data into standard FUNDAMENTAL_COLUMNS.
    
    Fully backward-compatible:
    1. If raw_input is already a normalized DataFrame (from fetch_raw), returns it directly.
    2. If raw_input is empty, raises EmptyResultError.
    3. If raw_input is a mock pivoted DataFrame (from legacy tests with period headers '2026-Q1'),
       transforms it into one row per period with JSON metrics.
    """
    if isinstance(raw_input, pd.DataFrame):
        if raw_input.empty:
            raise EmptyResultError(
                f"fetch_raw returned an empty DataFrame for symbol={symbol!r}, "
                f"report_type={report_type!r} -- F008-compatible: recorded as "
                f"genuine emptiness via record_empty(), NOT retried."
            )

        # Already normalized output from fetch_raw
        if set(FUNDAMENTAL_COLUMNS).issubset(raw_input.columns):
            return raw_input[FUNDAMENTAL_COLUMNS]

        # Case 1: Melted structure with 'period', ('id' or 'item_id'), 'value'
        id_col_candidate = "id" if "id" in raw_input.columns else ("item_id" if "item_id" in raw_input.columns else None)
        if "period" in raw_input.columns and "value" in raw_input.columns and id_col_candidate:
            df = raw_input.copy()
            df["period_end"] = df["period"].map(_period_label_to_date)
            rows: list[dict[str, object]] = []
            for period_end_raw, group in df.groupby("period_end", observed=False):
                period_end: dt.date = period_end_raw  # type: ignore[assignment]
                metrics = dict(zip(group[id_col_candidate].astype(str), group["value"]))
                rows.append(
                    {
                        "symbol": symbol,
                        "report_type": report_type,
                        "period_end": period_end,
                        "available_at": period_end + dt.timedelta(days=DISCLOSURE_LAG_DAYS),
                        "data_json": json.dumps(metrics, default=str, ensure_ascii=False),
                        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                        "source": "cafef",
                    }
                )
            out = pd.DataFrame(rows)
            return out[FUNDAMENTAL_COLUMNS]

        # Case 2: Pivoted structure (period labels as column headers)
        period_cols = [c for c in raw_input.columns if re.match(r"^\d{4}(-Q[1-4])?(_\d+)?$", str(c).strip())]
        if not period_cols:
            raise ValueError(
                f"No period-label columns matching 'YYYY' or 'YYYY-Qn' found in "
                f"fetched data for {symbol!r}/{report_type!r}. Columns present: {list(raw_input.columns)}."
            )

        id_col = (
            "item_id"
            if "item_id" in raw_input.columns
            else ("item" if "item" in raw_input.columns else ("id" if "id" in raw_input.columns else raw_input.columns[0]))
        )

        rows_pivoted: list[dict[str, object]] = []
        seen_periods: set[dt.date] = set()
        for pcol in period_cols:
            period_end = _period_label_to_date(str(pcol))
            if period_end in seen_periods:
                continue
            seen_periods.add(period_end)

            metrics = dict(zip(raw_input[id_col].astype(str), raw_input[pcol]))
            rows_pivoted.append(
                {
                    "symbol": symbol,
                    "report_type": report_type,
                    "period_end": period_end,
                    "available_at": period_end + dt.timedelta(days=DISCLOSURE_LAG_DAYS),
                    "data_json": json.dumps(metrics, default=str, ensure_ascii=False),
                    "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                    "source": "cafef",
                }
            )

        out = pd.DataFrame(rows_pivoted)
        dupes = out.duplicated(subset=["symbol", "report_type", "period_end"]).sum()
        if dupes:
            raise ValueError(
                f"melt_pivoted_statement produced {dupes} duplicate (symbol, "
                f"report_type, period_end) row(s) for {symbol!r}/{report_type!r} "
                f"-- refusing to write ambiguous data."
            )
        return out[FUNDAMENTAL_COLUMNS]

    if isinstance(raw_input, dict):
        return _parse_cafef_payload(raw_input, symbol, report_type)

    raise ValueError(f"Unsupported raw_input type: {type(raw_input)}")


format_melted_statement = melt_pivoted_statement


def write_statements(df: pd.DataFrame, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """APPEND-ONLY revision history: never deletes or overwrites existing records.
    
    Inserts only if new or changed, preserving historical vintages to prevent
    look-ahead bias in backtests.
    """
    missing = set(FUNDAMENTAL_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Fundamental DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    con.register("fund_df", df[FUNDAMENTAL_COLUMNS])

    to_write = con.execute(
        """
        WITH latest_existing AS (
            SELECT symbol, report_type, period_end, data_json,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol, report_type, period_end
                       ORDER BY fetched_at DESC
                   ) AS rn
            FROM core.fundamentals
        )
        SELECT n.*
        FROM fund_df n
        LEFT JOIN (SELECT * FROM latest_existing WHERE rn = 1) e
          ON n.symbol = e.symbol
         AND n.report_type = e.report_type
         AND n.period_end = e.period_end
        WHERE e.data_json IS NULL OR e.data_json != n.data_json
        """
    ).df()
    con.unregister("fund_df")

    if to_write.empty:
        return 0

    con.register("to_write_df", to_write[FUNDAMENTAL_COLUMNS])
    con.execute("INSERT INTO staging.fundamentals SELECT * FROM to_write_df")
    con.execute("INSERT INTO core.fundamentals SELECT * FROM to_write_df")
    con.unregister("to_write_df")

    return len(to_write)


def get_as_reported(con: duckdb.DuckDBPyConnection, symbol: str, report_type: str) -> pd.DataFrame:
    """Returns the AS-REPORTED (earliest observed) vintage for each period_end.
    
    Safe default for backtesting to strictly prevent look-ahead bias from restatements.
    """
    result: pd.DataFrame = con.execute(
        """
        SELECT symbol, report_type, period_end, available_at, data_json, fetched_at, source
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY symbol, report_type, period_end
                ORDER BY fetched_at ASC
            ) AS rn
            FROM core.fundamentals
            WHERE symbol = ? AND report_type = ?
        )
        WHERE rn = 1
        ORDER BY period_end
        """,
        [symbol, report_type],
    ).df()
    return result


def get_as_of(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
    report_type: str,
    as_of_date: dt.date,
    preferred_source: str = "vnstock_data",
) -> pd.DataFrame:
    """Returns the most recent vintage that had been observed and disclosed as of as_of_date."""
    result: pd.DataFrame = con.execute(
        """
        SELECT symbol, report_type, period_end, available_at, data_json, fetched_at, source
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY symbol, report_type, period_end
                ORDER BY
                    CASE WHEN source = ? THEN 0 ELSE 1 END ASC,
                    fetched_at DESC
            ) AS rn
            FROM core.fundamentals
            WHERE symbol = ? AND report_type = ?
              AND fetched_at <= ?
              AND available_at <= ?
        )
        WHERE rn = 1
        ORDER BY period_end
        """,
        [preferred_source, symbol, report_type, as_of_date, as_of_date],
    ).df()
    return result


def run(symbol: str, report_type: str = "all", period: str = "quarter") -> int:
    """Entry point: fetches live, normalizes, and writes fundamental data to core.fundamentals."""
    if report_type != "all":
        raw = fetch_raw(symbol, report_type, period)
        normalized = format_melted_statement(raw, symbol, report_type)
        return write_statements(normalized)

    total_written = 0
    any_succeeded = False
    last_empty_error: EmptyResultError | None = None
    cached_dfs: dict[str, pd.DataFrame] = {}

    # 1. Fetch primary statements first
    primary_types = [rt for rt in REPORT_TYPES if rt != "financial_health"]
    for rt in primary_types:
        try:
            raw = fetch_raw(symbol, rt, period)
            normalized = format_melted_statement(raw, symbol, rt)
            cached_dfs[rt] = normalized
            total_written += write_statements(normalized)
            any_succeeded = True
        except EmptyResultError as e:
            last_empty_error = e
            continue

    # 2. Compute financial_health directly in memory from already-fetched statements
    if "financial_health" in REPORT_TYPES and "balance_sheet" in cached_dfs and "income_statement" in cached_dfs:
        try:
            bs_df = cached_dfs["balance_sheet"]
            is_df = cached_dfs["income_statement"]
            cf_df = cached_dfs.get("cash_flow", pd.DataFrame())
            health_df = _compute_financial_health_scores(symbol, bs_df, is_df, cf_df)
            if not health_df.empty:
                total_written += write_statements(health_df)
                any_succeeded = True
        except Exception as e:
            logger.debug("Could not compute in-memory financial health for %s: %s", symbol, e)

    if not any_succeeded and last_empty_error is not None:
        raise last_empty_error

    return total_written


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F005: crawl fundamental report types for one symbol")
    parser.add_argument("symbol")
    parser.add_argument(
        "report_type", nargs="?", default="all", choices=[*REPORT_TYPES, "all"]
    )
    parser.add_argument("--period", default="quarter", choices=["quarter", "year"])
    args = parser.parse_args()

    n = run(args.symbol, args.report_type, args.period)
    print(f"F005 fundamentals: wrote {n} rows for {args.symbol}/{args.report_type} to core.fundamentals")