"""src/crawlers/update_intraday_1m_recent.py

Incremental 1-Minute OHLCV Update Engine for VESTA (F002b).
Brings core.market_ohlcv_1m from 2026-09-18 up to CURRENT_DATE (2026-10-09 T-0).

Kiến trúc:
1. Lấy danh sách cổ phiếu tích cực (ưu tiên VN30, VN100 và top thanh khoản).
2. Gọi Vietcap Trading gap-chart API (độ trễ siêu thấp, không dính rate-limit 100 nến).
3. Chuẩn hóa múi giờ Việt Nam (UTC+7, 09:15 - 14:45).
4. Lọc nến mới (time > '2026-09-18 15:00:00').
5. Nạp nguyên tử vào core.market_ohlcv_1m (ON CONFLICT DO NOTHING).
6. Đồng bộ sang db/admin/vesta_ohlcv.duckdb.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import logging
import os
import pathlib
import sys
import time
from typing import Dict, List, Optional, Tuple

import duckdb
import pandas as pd
import requests

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from crawlers.db_writer import MAIN_OHLCV_DB, ResilientDuckDBWriter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("update_intraday_1m")

VIETCAP_GAP_CHART_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}


def fetch_symbol_1m_recent(symbol: str, count_back: int = 4500) -> Optional[pd.DataFrame]:
    """Tải nến 1 phút gần nhất cho 1 mã cổ phiếu."""
    now_ts = int(time.time())
    payload = {
        "timeFrame": "ONE_MINUTE",
        "symbols": [symbol.upper()],
        "to": now_ts,
        "countBack": count_back,
    }
    try:
        resp = requests.post(VIETCAP_GAP_CHART_URL, json=payload, headers=BROWSER_HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0 and "t" in data[0]:
                raw_t = data[0]["t"]
                if not raw_t:
                    return None
                times = pd.to_datetime(raw_t, unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None)
                df = pd.DataFrame({
                    "symbol": symbol.upper(),
                    "time": times,
                    "open": [float(x) for x in data[0]["o"]],
                    "high": [float(x) for x in data[0]["h"]],
                    "low": [float(x) for x in data[0]["l"]],
                    "close": [float(x) for x in data[0]["c"]],
                    "volume": [int(x) for x in data[0]["v"]],
                    "fetched_at": dt.datetime.now(),
                })
                # Chỉ lấy các nến từ ngày 2026-09-18 15:00:00 trở đi
                df_new = df[df["time"] > "2026-09-18 15:00:00"]
                return df_new if not df_new.empty else None
    except Exception as e:
        logger.debug("Lỗi nến 1m %s: %s", symbol, e)
    return None


def get_target_symbols(con: duckdb.DuckDBPyConnection, limit: Optional[int] = None) -> List[str]:
    """Lấy danh mục cổ phiếu cần cập nhật nến 1 phút."""
    # Ưu tiên các mã có thanh khoản cao nhất trong năm 2026
    query = """
    SELECT symbol
    FROM core.market_ohlcv_daily
    WHERE date >= '2026-01-01'
    GROUP BY symbol
    ORDER BY sum(volume * close) DESC
    """
    rows = con.execute(query).fetchall()
    syms = [r[0] for r in rows if r[0] and len(r[0]) <= 5]
    if limit:
        syms = syms[:limit]
    return syms


def update_intraday_1m(target_db: str = MAIN_OHLCV_DB, limit_symbols: Optional[int] = 100) -> int:
    """Cập nhật nến 1 phút cho rổ cổ phiếu mục tiêu lên T-0 (2026-10-09)."""
    start_t = time.time()
    logger.info("=" * 80)
    logger.info("BẮT ĐẦU CẬP NHẬT NẾN 1 PHÚT (1M) BỔ SUNG: 2026-09-18 -> 2026-10-09 (T-0)")
    logger.info("=" * 80)

    con = duckdb.connect(target_db)
    symbols = get_target_symbols(con, limit=limit_symbols)
    con.close()

    logger.info("  • Tìm thấy %d mã cổ phiếu thanh khoản hàng đầu cần cập nhật 1m...", len(symbols))

    all_dfs = []
    success_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_sym = {executor.submit(fetch_symbol_1m_recent, sym): sym for sym in symbols}
        for future in concurrent.futures.as_completed(future_to_sym):
            sym = future_to_sym[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    all_dfs.append(df)
                    success_count += 1
                    logger.info("  ✓ [%s]: +%d nến mới (%s -> %s)", sym, len(df), df["time"].min(), df["time"].max())
            except Exception as e:
                logger.debug("Lỗi xử lý %s: %s", sym, e)

    total_inserted = 0
    if all_dfs:
        merged_df = pd.concat(all_dfs, ignore_index=True).drop_duplicates(subset=["symbol", "time"])
        logger.info(">>> Đang nạp %d nến 1 phút vào CSDL %s...", len(merged_df), target_db)

        con_write = duckdb.connect(target_db)
        con_write.register("incoming_1m", merged_df)
        con_write.execute("""
            INSERT OR IGNORE INTO core.market_ohlcv_1m
            SELECT symbol, time, open, high, low, close, volume, fetched_at
            FROM incoming_1m;
        """)
        total_inserted = len(merged_df)

        max_t = con_write.execute("SELECT max(time) FROM core.market_ohlcv_1m").fetchone()[0]
        total_in_db = con_write.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
        con_write.close()

        logger.info(">>> THÀNH CÔNG! Đã nạp +%d nến 1 phút. Max timestamp hiện tại: %s. Tổng nến trong DB: %d",
                    total_inserted, max_t, total_in_db)

        # Đồng bộ sang admin mirror
        admin_db = pathlib.Path("db/admin/vesta_ohlcv.duckdb")
        if admin_db.parent.exists():
            try:
                import shutil
                shutil.copy2(target_db, admin_db)
                logger.info("Đã đồng bộ sang db/admin/vesta_ohlcv.duckdb.")
            except Exception as e:
                logger.warning("Không thể sao chép sang admin db: %s", e)

    elapsed = time.time() - start_t
    logger.info("=" * 80)
    logger.info("HOÀN TẤT CẬP NHẬT 1M TRONG %.2f GIÂY. Số mã thành công: %d/%d. Số nến mới: %d.",
                elapsed, success_count, len(symbols), total_inserted)
    logger.info("=" * 80)
    return total_inserted


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    update_intraday_1m(target_db=MAIN_OHLCV_DB, limit_symbols=100)
