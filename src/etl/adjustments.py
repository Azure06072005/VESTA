"""
src/etl/adjustments.py

F002 Recommendation & F009: Corporate Actions & Ex-Dividend Price Adjustments.
Tích hợp công thức điều chỉnh giá tự động theo chuỗi nhân dồn (cumulative_adjustment_factor),
cho phép phân tích song song cả giá thô (đo bước giá thực tế) và giá điều chỉnh (đo tỷ suất sinh lời).

Công thức điều chỉnh kỹ thuật chuẩn của UBCKNN & Các Sở Giao Dịch (HOSE/HNX):
  P_ex = (P_close - D + P_add * beta) / (1 + alpha + beta)
  Hệ số điều chỉnh bước đơn: f = P_ex / P_close

Chuỗi nhân dồn tích lũy (Backward Cumulative Adjustment Factor - CAF):
  CAF(t) = Product(f_k) cho mọi ngày GDKHQ k có ex_date_k > t.
  P_adj(t) = P_raw(t) * CAF(t)  <=>  P_raw(t) = P_adj(t) / CAF(t)
  V_adj(t) = V_raw(t) / CAF(t)  <=>  V_raw(t) = V_adj(t) * CAF(t)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from etl import db  # noqa: E402


def compute_ssc_ex_price(
    p_close: float,
    cash_dividend: float = 0.0,
    stock_ratio: float = 0.0,
    rights_ratio: float = 0.0,
    rights_price: float = 0.0,
) -> Tuple[float, float]:
    """
    Tính giá tham chiếu ngày GDKHQ (P_ex) và hệ số điều chỉnh (f) theo quy định chuẩn của UBCKNN.
    Đơn vị: Nghìn VNĐ (tương thích với OHLCV của HOSE/HNX trên hệ thống).
    """
    if p_close <= 0:
        return p_close, 1.0

    # Nếu cổ tức tiền >= giá đóng cửa thì không điều chỉnh để tránh giá âm/bất thường
    if cash_dividend >= p_close:
        return p_close, 1.0

    numerator = p_close - cash_dividend + (rights_price * rights_ratio)
    denominator = 1.0 + stock_ratio + rights_ratio

    if denominator <= 0:
        return p_close, 1.0

    p_ex = numerator / denominator
    multiplier = p_ex / p_close

    # Giới hạn an toàn của multiplier trong [0.01, 1.0]
    multiplier = max(0.001, min(1.0, multiplier))
    return p_ex, multiplier


def compute_symbol_adjustments(
    symbol: str,
    sym_events: pd.DataFrame,
    sym_ohlcv: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Tính toán toàn bộ các sự kiện điều chỉnh giá và dựng chuỗi timeline CAF cho 1 mã cổ phiếu.
    Returns:
      (df_adj_events, df_timeline)
    """
    if sym_events.empty or sym_ohlcv.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Chuẩn bị dữ liệu OHLCV
    ohlcv_clean = sym_ohlcv.copy()
    ohlcv_clean["date"] = pd.to_datetime(ohlcv_clean["date"]).dt.date
    ohlcv_sorted = ohlcv_clean.sort_values("date").reset_index(drop=True)

    # 1. Trích xuất và gom nhóm sự kiện theo ngày GDKHQ (exright_date)
    actions_by_date = {}
    for _, row in sym_events.iterrows():
        try:
            detail_str = row["detail_json"]
            if not detail_str or str(detail_str).strip().lower() in ("nan", "none", ""):
                continue
            d = json.loads(detail_str) if isinstance(detail_str, str) else detail_str
            ex = d.get("exright_date")
            if not ex or str(ex).lower() in ("nan", "none", ""):
                continue
            ex_dt = pd.to_datetime(ex).date()
            code = str(d.get("event_code", "")).strip().upper()
            val = d.get("value_per_share")
            ratio = d.get("exercise_ratio")

            cash = 0.0
            stock = 0.0

            # Cổ tức tiền mặt: code 'DIV', value_per_share là số tiền VNĐ (chuyển sang nghìn VNĐ)
            if code == "DIV" and val is not None and not np.isnan(val) and float(val) > 0:
                cash = float(val) / 1000.0

            # Cổ tức cổ phiếu / Cổ phiếu thưởng: code 'ISS', exercise_ratio là tỷ lệ thưởng
            elif code == "ISS" and ratio is not None and not np.isnan(ratio) and float(ratio) > 0:
                stock = float(ratio)

            if cash > 0 or stock > 0:
                if ex_dt not in actions_by_date:
                    actions_by_date[ex_dt] = {"cash": 0.0, "stock": 0.0, "eids": []}
                actions_by_date[ex_dt]["cash"] += cash
                actions_by_date[ex_dt]["stock"] += stock
                eid = str(row.get("event_id", ""))
                if eid and eid not in actions_by_date[ex_dt]["eids"]:
                    actions_by_date[ex_dt]["eids"].append(eid)
        except Exception:
            continue

    if not actions_by_date:
        return pd.DataFrame(), pd.DataFrame()

    # 2. Tính toán P_ex và Multiplier từng ngày GDKHQ
    events_out = []
    for ex_dt in sorted(actions_by_date.keys()):
        act = actions_by_date[ex_dt]
        cash = act["cash"]
        stock = act["stock"]

        # Tìm giá close của ngày giao dịch liền trước
        prior = ohlcv_sorted[ohlcv_sorted["date"] < ex_dt]
        if prior.empty:
            continue
        cum_close = float(prior.iloc[-1]["close"])

        p_ex, multiplier = compute_ssc_ex_price(
            p_close=cum_close,
            cash_dividend=cash,
            stock_ratio=stock,
        )

        # Phân loại loại điều chỉnh
        if cash > 0 and stock > 0:
            adj_type = "COMBINED"
        elif cash > 0:
            adj_type = "CASH_DIVIDEND"
        else:
            adj_type = "STOCK_DIVIDEND"

        events_out.append({
            "symbol": symbol,
            "ex_date": ex_dt,
            "adjustment_type": adj_type,
            "cash_dividend": cash,
            "stock_dividend_ratio": stock,
            "cum_close_price": cum_close,
            "ex_reference_price": round(p_ex, 4),
            "multiplier": multiplier,
            "source_event_ids": ",".join(act["eids"]),
            "computed_at": dt.datetime.now(),
        })

    df_adj = pd.DataFrame(events_out)
    if df_adj.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_adj = df_adj.sort_values("ex_date").reset_index(drop=True)

    # 3. Tính Cumulative Adjustment Factor (CAF) theo chiều lùi từ mới nhất về cũ nhất
    n = len(df_adj)
    cafs = [1.0] * n
    running_product = 1.0
    for i in range(n - 1, -1, -1):
        running_product *= df_adj.loc[i, "multiplier"]
        cafs[i] = running_product
    df_adj["cumulative_adjustment_factor"] = cafs

    # 4. Xây dựng bảng timeline [start_date, end_date) -> caf
    timeline = []
    min_date = dt.date(1990, 1, 1)
    for i in range(n):
        ex_d = df_adj.loc[i, "ex_date"]
        timeline.append({
            "symbol": symbol,
            "start_date": min_date,
            "end_date": ex_d,
            "caf": df_adj.loc[i, "cumulative_adjustment_factor"],
        })
        min_date = ex_d

    # Khoảng cuối cùng: từ ngày ex_date gần nhất đến tương lai (CAF = 1.0)
    timeline.append({
        "symbol": symbol,
        "start_date": min_date,
        "end_date": dt.date(2099, 12, 31),
        "caf": 1.0,
    })

    df_timeline = pd.DataFrame(timeline)
    return df_adj, df_timeline


def build_and_sync_all_adjustments(
    con: Optional[duckdb.DuckDBPyConnection] = None,
    db_path: Optional[str] = None,
    symbols: Optional[List[str]] = None,
) -> Tuple[int, int]:
    """
    Quét toàn bộ dữ liệu sự kiện doanh nghiệp và OHLCV để tạo hệ thống điều chỉnh giá F002.
    Ghi kết quả vào core.price_adjustment_events và core.symbol_caf_timeline.
    """
    own_con = False
    if con is None:
        if db_path is None:
            snapshot_path = "d:/VESTA/db/vesta_snapshot.duckdb"
            db_path = snapshot_path if os.path.exists(snapshot_path) else "d:/VESTA/db/vesta.duckdb"
        con = duckdb.connect(db_path)
        own_con = True

    try:
        # Đảm bảo schema đã có bảng và view
        with open("configs/duckdb_schema.sql", "r", encoding="utf-8") as f:
            con.execute(f.read())

        # Lấy danh sách symbols cần tính
        if symbols is None:
            sym_rows = con.execute("SELECT DISTINCT symbol FROM core.corporate_events").fetchall()
            target_symbols = [r[0] for r in sym_rows]
        else:
            target_symbols = symbols

        logger.info(f"Bắt đầu tính toán CAF & sự kiện điều chỉnh giá cho {len(target_symbols)} mã...")

        # Load toàn bộ corporate events có liên quan đến DIV hoặc ISS
        ev_query = """
            SELECT symbol, event_id, event_type, event_date, detail_json
            FROM core.corporate_events
            WHERE detail_json ILIKE '%"event_code": "DIV"%' 
               OR detail_json ILIKE '%"event_code": "ISS"%'
               OR event_type = 'DIVIDEND'
        """
        all_events_df = con.execute(ev_query).df()

        # Load OHLCV daily cho các mã
        ohlcv_query = """
            SELECT symbol, date, close
            FROM core.market_ohlcv_daily
        """
        all_ohlcv_df = con.execute(ohlcv_query).df()
        all_ohlcv_df["date"] = pd.to_datetime(all_ohlcv_df["date"]).dt.date

        # Tối ưu hóa: Nhóm trước theo symbol để tra cứu O(1) thay vì lọc DataFrame 5.18M dòng 1028 lần
        events_by_sym = dict(tuple(all_events_df.groupby("symbol")))
        ohlcv_by_sym = dict(tuple(all_ohlcv_df.groupby("symbol")))

        all_adj_rows = []
        all_timeline_rows = []

        for sym in target_symbols:
            s_ev = events_by_sym.get(sym)
            s_ohlcv = ohlcv_by_sym.get(sym)
            if s_ev is None or s_ohlcv is None or s_ev.empty or s_ohlcv.empty:
                continue

            df_adj, df_time = compute_symbol_adjustments(sym, s_ev, s_ohlcv)
            if not df_adj.empty:
                all_adj_rows.append(df_adj)
            if not df_time.empty:
                all_timeline_rows.append(df_time)

        total_adj_events = 0
        total_timeline_intervals = 0

        # Ghi vào DuckDB
        if all_adj_rows:
            combined_adj = pd.concat(all_adj_rows, ignore_index=True)
            con.register("df_combined_adj", combined_adj)
            con.execute("""
                INSERT INTO core.price_adjustment_events (
                    symbol, ex_date, adjustment_type, cash_dividend, stock_dividend_ratio,
                    cum_close_price, ex_reference_price, multiplier, cumulative_adjustment_factor,
                    source_event_ids, computed_at
                )
                SELECT 
                    symbol, ex_date, adjustment_type, cash_dividend, stock_dividend_ratio,
                    cum_close_price, ex_reference_price, multiplier, cumulative_adjustment_factor,
                    source_event_ids, computed_at
                FROM df_combined_adj
                ON CONFLICT (symbol, ex_date) DO UPDATE SET
                    adjustment_type = EXCLUDED.adjustment_type,
                    cash_dividend = EXCLUDED.cash_dividend,
                    stock_dividend_ratio = EXCLUDED.stock_dividend_ratio,
                    cum_close_price = EXCLUDED.cum_close_price,
                    ex_reference_price = EXCLUDED.ex_reference_price,
                    multiplier = EXCLUDED.multiplier,
                    cumulative_adjustment_factor = EXCLUDED.cumulative_adjustment_factor,
                    source_event_ids = EXCLUDED.source_event_ids,
                    computed_at = EXCLUDED.computed_at;
            """)
            con.unregister("df_combined_adj")
            total_adj_events = len(combined_adj)

        if all_timeline_rows:
            combined_time = pd.concat(all_timeline_rows, ignore_index=True)
            con.register("df_combined_time", combined_time)
            con.execute("""
                INSERT INTO core.symbol_caf_timeline (symbol, start_date, end_date, caf)
                SELECT symbol, start_date, end_date, caf FROM df_combined_time
                ON CONFLICT (symbol, start_date) DO UPDATE SET
                    end_date = EXCLUDED.end_date,
                    caf = EXCLUDED.caf;
            """)
            con.unregister("df_combined_time")
            total_timeline_intervals = len(combined_time)

        logger.info(
            f"Hoàn thành F002: Đã nạp {total_adj_events} sự kiện điều chỉnh giá vào core.price_adjustment_events "
            f"và {total_timeline_intervals} khoảng timeline vào core.symbol_caf_timeline."
        )
        return total_adj_events, total_timeline_intervals

    finally:
        if own_con:
            con.close()


# =============================================================================
# BACKWARD COMPATIBILITY HELPERS (GIỮ TƯƠNG THÍCH VỚI PIPELINE CŨ)
# =============================================================================

def compute_adjustment_events(events_df: pd.DataFrame, ohlcv_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Hàm tương thích ngược cho các test suite cũ."""
    if events_df.empty:
        return pd.DataFrame(columns=["ex_date", "adjustment_type", "multiplier", "source_event_id"])

    ohlcv_clean = ohlcv_df.copy()
    ohlcv_clean["date"] = pd.to_datetime(ohlcv_clean["date"]).dt.date
    ohlcv_sorted = ohlcv_clean.sort_values("date").reset_index(drop=True)
    rows = []

    for _, event in events_df.iterrows():
        try:
            detail_str = event["detail_json"]
            if not detail_str or str(detail_str).strip().lower() in ("nan", "none", ""):
                continue
            detail = json.loads(detail_str) if isinstance(detail_str, str) else detail_str
        except Exception:
            continue

        exright_date_str = detail.get("exright_date")
        if not exright_date_str or str(exright_date_str).strip().lower() in ("nan", "none", ""):
            continue
        try:
            ex_date = pd.to_datetime(exright_date_str).date()
        except Exception:
            continue

        event_code = detail.get("event_code")

        def _parse_flt(val):
            if val is None or str(val).strip().lower() in ("nan", "none", ""):
                return None
            try:
                return float(val)
            except Exception:
                return None

        exercise_ratio = _parse_flt(detail.get("exercise_ratio"))
        value_per_share = _parse_flt(detail.get("value_per_share"))

        if event_code == "ISS" and exercise_ratio is not None and exercise_ratio > 0:
            multiplier = 1.0 / (1.0 + exercise_ratio)
            adjustment_type = "share_issue"
        elif event.get("event_type") == "DIVIDEND" and value_per_share is not None and value_per_share > 0:
            prior = ohlcv_sorted[ohlcv_sorted["date"] < ex_date]
            if prior.empty:
                continue
            cum_close = float(prior.iloc[-1]["close"])
            if cum_close <= value_per_share:
                continue
            multiplier = (cum_close - value_per_share) / cum_close
            adjustment_type = "dividend"
        else:
            continue

        rows.append({
            "ex_date": ex_date,
            "adjustment_type": adjustment_type,
            "multiplier": multiplier,
            "source_event_id": event["event_id"],
        })

    return pd.DataFrame(rows, columns=["ex_date", "adjustment_type", "multiplier", "source_event_id"])


def write_adjustment_events(df: pd.DataFrame, symbol: str, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Hàm ghi tương thích ngược cho các test suite cũ."""
    if df.empty:
        return 0

    con = con or db.bootstrap_schema()
    for _, row in df.iterrows():
        con.execute("""
            INSERT INTO core.price_adjustment_events (
                symbol, ex_date, adjustment_type, multiplier, cumulative_adjustment_factor, source_event_ids, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (symbol, ex_date) DO UPDATE SET
                adjustment_type = EXCLUDED.adjustment_type,
                multiplier = EXCLUDED.multiplier,
                source_event_ids = EXCLUDED.source_event_ids;
        """, [symbol, row["ex_date"], row["adjustment_type"], row["multiplier"], row["multiplier"], row["source_event_id"]])
    return len(df)


def get_adjustment_factor(adjustment_events_df: pd.DataFrame, as_of_date: dt.date | pd.Timestamp) -> float:
    """Cumulative multiplier áp dụng cho ngày as_of_date (backward compatibility)."""
    if adjustment_events_df.empty:
        return 1.0
    ex_dates = pd.to_datetime(adjustment_events_df["ex_date"])
    target_ts = pd.to_datetime(as_of_date)
    applicable = adjustment_events_df[ex_dates > target_ts]
    if applicable.empty:
        return 1.0
    values = [float(v) for v in applicable["multiplier"].tolist()]
    product = 1.0
    for v in values:
        product *= v
    return product


def apply_adjustment(ohlcv_df: pd.DataFrame, adjustment_events_df: pd.DataFrame) -> pd.DataFrame:
    """Trả về ohlcv_df có thêm các cột adj_open/high/low/close (backward compatibility)."""
    out = ohlcv_df.copy()
    out["adj_factor"] = out["date"].apply(lambda d: get_adjustment_factor(adjustment_events_df, d))
    for col in ("open", "high", "low", "close"):
        out[f"adj_{col}"] = out[col] * out["adj_factor"]
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    build_and_sync_all_adjustments()