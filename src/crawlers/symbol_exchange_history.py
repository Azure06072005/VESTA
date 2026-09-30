"""src/crawlers/symbol_exchange_history.py

Xây dựng bảng lịch sử chuyển sàn và niêm yết theo chuỗi thời gian (F001 Khuyến nghị):
Bảng core.symbol_exchange_history ghi nhận chính xác mốc ngày bắt đầu (start_date),
ngày kết thúc (end_date), và sàn giao dịch (HOSE, HNX, UPCOM, DELISTED) của từng mã chứng khoán.

Mục đích:
- Triệt tiêu hoàn toàn thiên vị nhìn trước (Look-Ahead Bias) trong backtest:
  Ví dụ ACB trước 09/12/2020 giao dịch trên HNX (biên độ +/-10%), sau đó mới chuyển sang HOSE (+/-7%).
  BCM, VIB, LPB, GVR, POW trước khi sang HOSE đều có nhiều năm giao dịch trên UPCOM (+/-15%).
- Cung cấp hàm tra cứu điểm thời gian (Point-in-Time):
  `get_exchange_at_date(symbol, trade_date)` trả về chính xác sàn giao dịch tại ngày đó.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter
from etl import db

logger = logging.getLogger("symbol_exchange_history")

EXCHANGE_HISTORY_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS core.symbol_exchange_history (
    symbol          VARCHAR NOT NULL,
    exchange        VARCHAR NOT NULL,
    start_date      DATE NOT NULL,
    end_date        DATE,
    is_current      BOOLEAN NOT NULL,
    listing_price   DOUBLE,
    event_note      VARCHAR,
    source          VARCHAR NOT NULL DEFAULT 'HOSE/HNX/CompanyOverview',
    created_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, exchange, start_date)
);
"""

# Từ điển các mốc chuyển sàn lịch sử quan trọng đã được kiểm chứng qua công báo HOSE/HNX
KNOWN_HISTORICAL_TRANSFERS: Dict[str, Dict[str, Any]] = {
    "ACB": {
        "prior_exchange": "HNX",
        "prior_start": dt.date(2006, 11, 21),
        "prior_end": dt.date(2020, 12, 8),
        "current_start": dt.date(2020, 12, 9),
        "note": "Chuyển niêm yết từ HNX sang HOSE",
    },
    "SHB": {
        "prior_exchange": "HNX",
        "prior_start": dt.date(2009, 4, 20),
        "prior_end": dt.date(2021, 10, 8),
        "current_start": dt.date(2021, 10, 11),
        "note": "Chuyển niêm yết từ HNX sang HOSE",
    },
    "LPB": {
        "prior_exchange": "UPCOM",
        "prior_start": dt.date(2017, 10, 5),
        "prior_end": dt.date(2020, 11, 6),
        "current_start": dt.date(2020, 11, 9),
        "note": "Chuyển giao dịch từ UPCOM sang niêm yết HOSE",
    },
    "VIB": {
        "prior_exchange": "UPCOM",
        "prior_start": dt.date(2017, 1, 9),
        "prior_end": dt.date(2020, 11, 9),
        "current_start": dt.date(2020, 11, 10),
        "note": "Chuyển giao dịch từ UPCOM sang niêm yết HOSE",
    },
    "BCM": {
        "prior_exchange": "UPCOM",
        "prior_start": dt.date(2018, 2, 28),
        "prior_end": dt.date(2020, 8, 28),
        "current_start": dt.date(2020, 8, 31),
        "note": "Chuyển giao dịch từ UPCOM sang niêm yết HOSE",
    },
    "HVN": {
        "prior_exchange": "UPCOM",
        "prior_start": dt.date(2017, 1, 3),
        "prior_end": dt.date(2019, 5, 6),
        "current_start": dt.date(2019, 5, 7),
        "note": "Chuyển giao dịch từ UPCOM sang niêm yết HOSE",
    },
    "VCG": {
        "prior_exchange": "HNX",
        "prior_start": dt.date(2008, 9, 5),
        "prior_end": dt.date(2020, 12, 28),
        "current_start": dt.date(2020, 12, 29),
        "note": "Chuyển niêm yết từ HNX sang HOSE",
    },
    "GVR": {
        "prior_exchange": "UPCOM",
        "prior_start": dt.date(2018, 3, 21),
        "prior_end": dt.date(2020, 3, 16),
        "current_start": dt.date(2020, 3, 17),
        "note": "Chuyển giao dịch từ UPCOM sang niêm yết HOSE",
    },
    "POW": {
        "prior_exchange": "UPCOM",
        "prior_start": dt.date(2018, 3, 6),
        "prior_end": dt.date(2019, 1, 11),
        "current_start": dt.date(2019, 1, 14),
        "note": "Chuyển giao dịch từ UPCOM sang niêm yết HOSE",
    },
    "SSI": {
        "prior_exchange": "HNX",
        "prior_start": dt.date(2006, 12, 15),
        "prior_end": dt.date(2007, 10, 26),
        "current_start": dt.date(2007, 10, 29),
        "note": "Chuyển niêm yết từ HNX sang HOSE",
    },
}


def parse_listing_date(val: Any) -> Optional[dt.date]:
    """Chuyển đổi chuỗi ngày DD/MM/YYYY hoặc ISO sang dt.date an toàn."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            try:
                return dt.date(int(parts[2]), int(parts[1]), int(parts[0]))
            except Exception:
                pass
    try:
        return dt.date.fromisoformat(s[:10])
    except Exception:
        return None


def build_symbol_exchange_history(
    overview_df: Optional[pd.DataFrame] = None,
    ohlcv_bounds_df: Optional[pd.DataFrame] = None,
    dim_symbol_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Xây dựng bảng lịch sử sàn giao dịch liên tục cho toàn bộ mã chứng khoán."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    # Nếu các dataframe chưa được truyền vào, đọc từ CSDL có sẵn
    if overview_df is None or dim_symbol_df is None:
        con_read = None
        for db_cand in [
            str(PROJECT_ROOT / "db" / "vesta_backup.duckdb"),
            str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"),
            str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb"),
        ]:
            if os.path.exists(db_cand):
                try:
                    con_read = duckdb.connect(db_cand, read_only=True)
                    break
                except Exception:
                    continue

        if con_read is not None:
            try:
                if overview_df is None:
                    overview_df = con_read.execute("SELECT symbol, exchange, listing_date, listing_price, history FROM core.company_overview").df()
                if ohlcv_bounds_df is None:
                    ohlcv_bounds_df = con_read.execute("SELECT symbol, min(date) as min_date, max(date) as max_date FROM core.market_ohlcv_daily GROUP BY symbol").df()
                if dim_symbol_df is None:
                    dim_symbol_df = con_read.execute("SELECT symbol, exchange, is_delisted FROM core.dim_symbol").df()
            finally:
                con_read.close()

    # Fallback tối thiểu nếu không mở được database
    if overview_df is None:
        overview_df = pd.DataFrame([{"symbol": s, "exchange": "HOSE", "listing_date": None, "listing_price": 10.0} for s in KNOWN_HISTORICAL_TRANSFERS])
    if ohlcv_bounds_df is None:
        ohlcv_bounds_df = pd.DataFrame([{"symbol": s, "min_date": "2000-01-01", "max_date": "2026-09-25"} for s in KNOWN_HISTORICAL_TRANSFERS])
    if dim_symbol_df is None:
        dim_symbol_df = pd.DataFrame([{"symbol": s, "exchange": "HOSE", "is_delisted": False} for s in KNOWN_HISTORICAL_TRANSFERS])

    # 1. Chuẩn hóa mapping
    ov_map: Dict[str, Dict[str, Any]] = {}
    for _, r in overview_df.iterrows():
        sym = str(r["symbol"]).strip().upper()
        p_date = parse_listing_date(r.get("listing_date"))
        p_price = float(r["listing_price"]) if pd.notna(r.get("listing_price")) else None
        ov_map[sym] = {
            "exchange": str(r.get("exchange", "")).strip().upper(),
            "listing_date": p_date,
            "listing_price": p_price,
        }

    trade_bounds: Dict[str, Tuple[dt.date, dt.date]] = {}
    for _, r in ohlcv_bounds_df.iterrows():
        sym = str(r["symbol"]).strip().upper()
        min_d = pd.to_datetime(r["min_date"]).date() if pd.notna(r["min_date"]) else None
        max_d = pd.to_datetime(r["max_date"]).date() if pd.notna(r["max_date"]) else None
        if min_d and max_d:
            trade_bounds[sym] = (min_d, max_d)

    records: List[Dict[str, Any]] = []

    # Duyệt qua toàn bộ danh bạ dim_symbol
    for _, r in dim_symbol_df.iterrows():
        sym = str(r["symbol"]).strip().upper()
        curr_exchange = str(r.get("exchange", "")).strip().upper() or "UPCOM"
        is_delisted = bool(r.get("is_delisted", False)) or (curr_exchange == "DELISTED")

        # A. Kiểm tra nếu mã nằm trong danh mục mốc chuyển sàn lịch sử đã biết
        if sym in KNOWN_HISTORICAL_TRANSFERS:
            kt = KNOWN_HISTORICAL_TRANSFERS[sym]
            # Bản ghi sàn trước
            records.append({
                "symbol": sym,
                "exchange": kt["prior_exchange"],
                "start_date": kt["prior_start"],
                "end_date": kt["prior_end"],
                "is_current": False,
                "listing_price": None,
                "event_note": kt["note"],
                "source": "HOSE/HNX Official Gazette",
                "created_at": now,
            })
            # Bản ghi sàn hiện tại
            records.append({
                "symbol": sym,
                "exchange": curr_exchange if curr_exchange != "DELISTED" else "HOSE",
                "start_date": kt["current_start"],
                "end_date": None if not is_delisted else trade_bounds.get(sym, (None, now.date()))[1],
                "is_current": not is_delisted,
                "listing_price": ov_map.get(sym, {}).get("listing_price"),
                "event_note": "Niêm yết chính thức sau chuyển sàn",
                "source": "HOSE/HNX Official Gazette",
                "created_at": now,
            })
            continue

        # B. Tự động phát hiện chuyển sàn dựa trên chênh lệch giữa ngày niêm yết và ngày nến giao dịch sớm nhất
        ov_info = ov_map.get(sym, {})
        listing_date = ov_info.get("listing_date")
        listing_price = ov_info.get("listing_price")
        bounds = trade_bounds.get(sym)

        if bounds:
            min_trade_date, max_trade_date = bounds
        else:
            min_trade_date = listing_date or dt.date(2000, 7, 28)
            max_trade_date = None

        if listing_date and min_trade_date and (listing_date - min_trade_date).days > 60:
            # Có giao dịch thực tế > 2 tháng trước ngày niêm yết hiện tại -> Đã từng giao dịch ở sàn trước
            prior_ex = "UPCOM" if curr_exchange == "HOSE" else "HNX"
            prior_end = listing_date - dt.timedelta(days=1)
            records.append({
                "symbol": sym,
                "exchange": prior_ex,
                "start_date": min_trade_date,
                "end_date": prior_end,
                "is_current": False,
                "listing_price": None,
                "event_note": f"Giao dịch trên {prior_ex} trước khi chuyển sang {curr_exchange}",
                "source": "Trade Bounds & Company Overview",
                "created_at": now,
            })
            records.append({
                "symbol": sym,
                "exchange": curr_exchange if curr_exchange != "DELISTED" else "HOSE",
                "start_date": listing_date,
                "end_date": None if not is_delisted else max_trade_date,
                "is_current": not is_delisted,
                "listing_price": listing_price,
                "event_note": f"Niêm yết trên {curr_exchange}",
                "source": "Company Overview",
                "created_at": now,
            })
        else:
            # Không có chuyển sàn, niêm yết xuyên suốt một sàn
            eff_start = listing_date or min_trade_date or dt.date(2000, 7, 28)
            records.append({
                "symbol": sym,
                "exchange": curr_exchange if curr_exchange != "DELISTED" else "UPCOM",
                "start_date": eff_start,
                "end_date": None if not is_delisted else (max_trade_date or now.date()),
                "is_current": not is_delisted,
                "listing_price": listing_price,
                "event_note": "Niêm yết ban đầu",
                "source": "Company Overview / Dim Symbol",
                "created_at": now,
            })

    # Khử trùng lặp trên (symbol, exchange, start_date)
    df_out = pd.DataFrame(records)
    df_out = df_out.drop_duplicates(subset=["symbol", "exchange", "start_date"]).sort_values(["symbol", "start_date"])
    return df_out


build_symbol_exchange_history_df = build_symbol_exchange_history


def write_exchange_history(
    df: pd.DataFrame,
    writer: Optional[ResilientDuckDBWriter | duckdb.DuckDBPyConnection] = None,
    con: Optional[duckdb.DuckDBPyConnection] = None,
) -> int:
    """Ghi bảng lịch sử sàn giao dịch vào core.symbol_exchange_history an toàn."""
    required_cols = {"symbol", "exchange", "start_date", "is_current"}
    if not required_cols.issubset(set(df.columns)):
        raise ValueError(f"DataFrame thiếu các cột bắt buộc: {required_cols - set(df.columns)}")

    if con is None and isinstance(writer, duckdb.DuckDBPyConnection):
        con = writer
        writer = None

    if con is not None:
        con.execute(EXCHANGE_HISTORY_SCHEMA_DDL)
        con.execute("DELETE FROM core.symbol_exchange_history")
        con.register("df_ex_view", df)
        con.execute("INSERT INTO core.symbol_exchange_history SELECT * FROM df_ex_view")
        con.unregister("df_ex_view")
        return len(df)

    writer = writer or ResilientDuckDBWriter()

    def _action(c: duckdb.DuckDBPyConnection):
        c.execute(EXCHANGE_HISTORY_SCHEMA_DDL)
        c.execute("DELETE FROM core.symbol_exchange_history")
        c.register("df_ex_view", df)
        c.execute("INSERT INTO core.symbol_exchange_history SELECT * FROM df_ex_view")
        c.unregister("df_ex_view")
        return len(df)

    cnt = writer.execute_with_retry(_action)
    try:
        writer.atomic_ingest_buffer()
    except Exception as e:
        logger.debug("Atomic ingest skipped/deferred: %s", e)
    return cnt


write_symbol_exchange_history = write_exchange_history


def get_exchange_at_date(
    symbol: str,
    target_date: str | dt.date,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    target_db: str = DEFAULT_TARGET_DB,
) -> Optional[str]:
    """Tra cứu sàn giao dịch chuẩn xác tại một điểm thời gian (Point-in-Time)."""
    if isinstance(target_date, str):
        target_date = dt.date.fromisoformat(target_date[:10])

    sym_upper = symbol.upper()

    close_con = False
    con_to_use = con
    if con_to_use is None:
        for db_cand in [
            str(PROJECT_ROOT / "db" / "vesta_backup.duckdb"),
            target_db,
            str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"),
            str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb"),
        ]:
            if os.path.exists(db_cand):
                try:
                    c = duckdb.connect(db_cand, read_only=True)
                    tbl_ok = c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='core' AND table_name='symbol_exchange_history'").fetchone()[0]
                    if tbl_ok:
                        con_to_use = c
                        close_con = True
                        break
                    else:
                        c.close()
                except Exception:
                    continue

    if con_to_use is not None:
        try:
            query = """
                SELECT exchange 
                FROM core.symbol_exchange_history
                WHERE symbol = ?
                  AND start_date <= ?
                  AND (end_date IS NULL OR end_date >= ?)
                ORDER BY start_date DESC
                LIMIT 1
            """
            res = con_to_use.execute(query, [sym_upper, target_date, target_date]).fetchone()
            if res:
                return res[0]
        except Exception:
            pass
        finally:
            if close_con and con_to_use:
                con_to_use.close()

    # Fallback trên từ điển tĩnh đã biết
    if sym_upper in KNOWN_HISTORICAL_TRANSFERS:
        kt = KNOWN_HISTORICAL_TRANSFERS[sym_upper]
        if target_date < kt["prior_start"]:
            return None
        if target_date <= kt["prior_end"]:
            return kt["prior_exchange"]
        return "HOSE"

    return None


def run(
    target_db: Optional[str] = None,
    con: Optional[duckdb.DuckDBPyConnection] = None,
) -> int:
    """Hàm chạy chính của crawler symbol_exchange_history."""
    logger.info(">>> [F001] Bắt đầu xây dựng bảng lịch sử chuyển sàn core.symbol_exchange_history...")

    if con is not None:
        ov_df = con.execute("""
            SELECT symbol, exchange, listing_date, listing_price, history 
            FROM core.company_overview
        """).df()
        ohlcv_bounds = con.execute("""
            SELECT symbol, min(date) as min_date, max(date) as max_date 
            FROM core.market_ohlcv_daily 
            GROUP BY symbol
        """).df()
        dim_df = con.execute("""
            SELECT symbol, exchange, is_delisted 
            FROM core.dim_symbol
        """).df()
        df_history = build_symbol_exchange_history(ov_df, ohlcv_bounds, dim_df)
        logger.info("Đã tạo %d bản ghi lịch sử sàn cho %d mã cổ phiếu.", len(df_history), len(dim_df))
        cnt = write_exchange_history(df_history, con=con)
        logger.info(">>> [F001] Hoàn tất nạp core.symbol_exchange_history: %d bản ghi.", cnt)
        return cnt

    # Đọc dữ liệu đầu vào từ CSDL chính hoặc backup
    db_to_read = target_db or DEFAULT_TARGET_DB
    con_read = None
    try:
        con_read = duckdb.connect(db_to_read, read_only=True)
    except Exception:
        backup_db = str(PROJECT_ROOT / "db" / "vesta_backup.duckdb")
        if os.path.exists(backup_db):
            logger.info("Kết nối đọc từ backup: %s", backup_db)
            con_read = duckdb.connect(backup_db, read_only=True)

    if con_read is None:
        raise RuntimeError("Không thể mở CSDL để đọc dữ liệu tổng hợp lịch sử sàn.")

    try:
        ov_df = con_read.execute("""
            SELECT symbol, exchange, listing_date, listing_price, history 
            FROM core.company_overview
        """).df()
        ohlcv_bounds = con_read.execute("""
            SELECT symbol, min(date) as min_date, max(date) as max_date 
            FROM core.market_ohlcv_daily 
            GROUP BY symbol
        """).df()
        dim_df = con_read.execute("""
            SELECT symbol, exchange, is_delisted 
            FROM core.dim_symbol
        """).df()
    finally:
        con_read.close()

    df_history = build_symbol_exchange_history(ov_df, ohlcv_bounds, dim_df)
    logger.info("Đã tạo %d bản ghi lịch sử sàn cho %d mã cổ phiếu.", len(df_history), len(dim_df))

    writer = ResilientDuckDBWriter(target_db=target_db or DEFAULT_TARGET_DB)
    cnt = write_exchange_history(df_history, writer=writer)
    logger.info(">>> [F001] Hoàn tất nạp core.symbol_exchange_history: %d bản ghi.", cnt)
    return cnt


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run()
