"""src/crawlers/order_book_depth_vietcap.py

Crawler Sổ lệnh vi mô Level 2 Depth & Khớp lệnh Intraday cho rổ VN100.
Kiến trúc 100% Direct REST API (Zero vnstock / Zero API Key dependency):
- Nguồn: Vietcap Direct REST API (https://trading.vietcap.com.vn/api/price/symbols/getList)
- Danh mục: Rổ chỉ số VN100 (100 cổ phiếu vốn hóa & thanh khoản hàng đầu HOSE)
- Dữ liệu thu thập:
  1. Top 3 mức giá Mua / Bán tốt nhất (Bid 1-3, Ask 1-3) & Khối lượng.
  2. Tổng độ sâu mua / bán (Total Bid / Ask Depth), Chênh lệch Spread.
  3. Chỉ số Mất cân bằng Dòng lệnh (Order Flow Imbalance - OFI Ratio).
  4. Thông tin khớp lệnh gần nhất (Matched Price, Matched Volume, Foreign Buy/Sell).
- Ghi vào: `staging.order_book_depth`, `core.order_book_depth`, `core.intraday_trades`
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawlers.order_book_vietcap")

VIETCAP_URL = "https://trading.vietcap.com.vn/api/price/symbols/getList"
VIETCAP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn/",
}


def get_vn100_symbols(db_path: str = "db/vesta_snapshot.duckdb") -> List[str]:
    """Lấy danh sách 100 mã cổ phiếu rổ VN100 từ CSDL VESTA."""
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute("""
            SELECT DISTINCT symbol 
            FROM core.dim_index_constituents 
            WHERE index_code = 'VN100'
            ORDER BY symbol
        """).fetchall()
        symbols = [r[0] for r in rows]
        if not symbols:
            # Fallback nếu bảng chưa có: lấy top 100 mã vốn hóa lớn nhất HOSE
            rows_fb = con.execute("""
                SELECT symbol FROM core.dim_symbol WHERE exchange = 'HOSE' LIMIT 100
            """).fetchall()
            symbols = [r[0] for r in rows_fb]
        return symbols
    finally:
        con.close()


def fetch_vietcap_batch(symbols: List[str], timeout: int = 10) -> List[Dict[str, Any]]:
    """Gửi request lấy dữ liệu sổ lệnh và giá từ Vietcap Direct API."""
    payload = json.dumps({"symbols": [s.upper() for s in symbols]}).encode("utf-8")
    req = urllib.request.Request(VIETCAP_URL, data=payload, headers=VIETCAP_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def crawl_order_book_vn100(
    db_path: str = "db/vesta_snapshot.duckdb",
    batch_size: int = 25,
) -> Dict[str, int]:
    """Cào toàn bộ rổ VN100, tính toán OFI và ghi nhận vào DuckDB."""
    symbols = get_vn100_symbols(db_path)
    logger.info(">>> BẮT ĐẦU CÀO ORDER BOOK LEVEL 2 CHO RỔ VN100 (%d MÃ) QUA VIETCAP DIRECT API...", len(symbols))

    raw_items: List[Dict[str, Any]] = []
    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i : i + batch_size]
        try:
            items = fetch_vietcap_batch(chunk)
            raw_items.extend(items)
            logger.info("  • Batch %d/%d: Thu thập thành công %d mã.", i // batch_size + 1, (len(symbols) + batch_size - 1) // batch_size, len(items))
        except Exception as e:
            logger.error("  ❌ Lỗi batch %s: %s", chunk, e)
        time.sleep(0.15)

    now_utc = dt.datetime.now(dt.timezone.utc)
    now_local = dt.datetime.now()

    ob_rows: List[Dict[str, Any]] = []
    trade_rows: List[Dict[str, Any]] = []

    for item in raw_items:
        sym = item.get("listingInfo", {}).get("symbol")
        if not sym:
            continue

        ba = item.get("bidAsk", {})
        bids = ba.get("bidPrices", [])
        asks = ba.get("askPrices", [])

        # Trích xuất 3 mức giá Mua / Bán
        p_b1 = bids[0].get("price") if len(bids) > 0 else None
        v_b1 = bids[0].get("volume") if len(bids) > 0 else None
        p_b2 = bids[1].get("price") if len(bids) > 1 else None
        v_b2 = bids[1].get("volume") if len(bids) > 1 else None
        p_b3 = bids[2].get("price") if len(bids) > 2 else None
        v_b3 = bids[2].get("volume") if len(bids) > 2 else None

        p_a1 = asks[0].get("price") if len(asks) > 0 else None
        v_a1 = asks[0].get("volume") if len(asks) > 0 else None
        p_a2 = asks[1].get("price") if len(asks) > 1 else None
        v_a2 = asks[1].get("volume") if len(asks) > 1 else None
        p_a3 = asks[2].get("price") if len(asks) > 2 else None
        v_a3 = asks[2].get("volume") if len(asks) > 2 else None

        tot_bid = sum(filter(None, [v_b1, v_b2, v_b3]))
        tot_ask = sum(filter(None, [v_a1, v_a2, v_a3]))
        spread = (p_a1 - p_b1) if (p_a1 and p_b1) else None
        ofi = (tot_bid - tot_ask) / (tot_bid + tot_ask) if (tot_bid + tot_ask) > 0 else 0.0

        ob_rows.append({
            "symbol": sym,
            "timestamp": now_local,
            "bid_price_1": p_b1,
            "bid_vol_1": v_b1,
            "bid_price_2": p_b2,
            "bid_vol_2": v_b2,
            "bid_price_3": p_b3,
            "bid_vol_3": v_b3,
            "ask_price_1": p_a1,
            "ask_vol_1": v_a1,
            "ask_price_2": p_a2,
            "ask_vol_2": v_a2,
            "ask_price_3": p_a3,
            "ask_vol_3": v_a3,
            "total_bid_depth": float(tot_bid),
            "total_ask_depth": float(tot_ask),
            "spread": float(spread) if spread is not None else None,
            "ofi_ratio": round(float(ofi), 6),
            "fetched_at": now_local,
        })

        # Trích xuất giao dịch khớp lệnh gần nhất
        mp = item.get("matchPrice", {})
        match_p = mp.get("matchPrice")
        match_v = mp.get("matchVol")
        if match_p and match_v:
            trade_id = f"{now_local.strftime('%Y%m%d')}_{sym}_{mp.get('id', '0')}"
            trade_rows.append({
                "symbol": sym,
                "trade_id": trade_id,
                "time": now_local,
                "price": float(match_p),
                "volume": int(match_v),
                "match_type": mp.get("matchType", "UNKNOWN"),
                "is_shark_sweep": bool(match_v >= 50000),  # Lệnh lớn >= 50k cổ phiếu
                "fetched_at": now_local,
            })

    # Ghi nhận vào DuckDB
    con = duckdb.connect(db_path, read_only=False)
    try:
        df_ob = pd.DataFrame(ob_rows)
        con.execute("INSERT OR REPLACE INTO core.order_book_depth SELECT * FROM df_ob;")
        con.execute("INSERT INTO staging.order_book_depth SELECT * FROM df_ob;")

        if trade_rows:
            df_trades = pd.DataFrame(trade_rows)
            con.execute("INSERT OR REPLACE INTO core.intraday_trades SELECT * FROM df_trades;")

        con.execute("CHECKPOINT;")
    finally:
        con.close()

    logger.info("🎉 HOÀN TẤT: Đã ghi +%d bản ghi Order Book Depth & +%d bản ghi Trades vào %s!", len(ob_rows), len(trade_rows), db_path)
    return {"order_book_records": len(ob_rows), "intraday_trades": len(trade_rows)}


if __name__ == "__main__":
    for db_target in ["db/vesta_snapshot.duckdb", "db/vesta_backup.duckdb"]:
        if os.path.exists(db_target):
            crawl_order_book_vn100(db_target)
