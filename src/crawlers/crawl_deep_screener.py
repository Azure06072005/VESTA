"""src/crawlers/crawl_deep_screener.py

Crawler Bộ lọc Cổ phiếu Đa Nhân tố Chuyên sâu (Deep Screener Crawler).
Kiến trúc 100% Direct REST API (Zero vnstock / Zero API Key dependency):
- Nguồn: Vietcap IQ Direct Screening API (https://iq.vietcap.com.vn/api/iq-insight-service/v1/screening/paging)
- Đối tượng: Toàn bộ cổ phiếu niêm yết (HSX, HNX, UPCOM) ~1,522 mã (ALL SYMBOLS).
- Thời gian: Max date (Ngày giao dịch mới nhất).
- Các chỉ số bóc tách chuyên sâu:
  1. Định giá & Lợi nhuận (Fundamental): P/E (ttmPe), P/B (ttmPb), ROE (ttmRoe), Biên LN gộp (grossMargin), Biên LN ròng (netMargin), Tăng trưởng LNST (npatmiGrowth), Tăng trưởng Doanh thu (revenueGrowth).
  2. Kỹ thuật & Xung lực (Technical/Momentum): Sức mạnh giá RS, RSI, Điểm kỹ thuật stockStrength, ADTV 10 ngày, Thanh khoản đột biến.
  3. Giá & Vốn hóa: Thị giá, Giá tham chiếu, Giá trần, Giá sàn, Vốn hóa thị trường, Khối lượng giao dịch, Giá trị giao dịch.
  4. Phân ngành: Ngành cấp 2, cấp 4 (ICB Code).
- Ghi nhận: Lưu vào `staging.market_screener_snapshot` & `core.market_screener_snapshot` với đầy đủ các cột và `data_json`.
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
logger = logging.getLogger("crawlers.deep_screener")

SCREENER_URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/screening/paging"
SCREENER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}


def fetch_deep_screener_data(page_size: int = 2000, timeout: int = 20) -> List[Dict[str, Any]]:
    """Truy vấn dữ liệu bộ lọc đa nhân tố chuyên sâu từ Vietcap IQ API."""
    logger.info("Đang gửi yêu cầu Deep Screener tới Vietcap IQ API (page_size=%d)...", page_size)
    
    # Cấu hình bộ lọc bao quát tất cả sàn và yêu cầu trả về các trường tài chính chuyên sâu
    payload = {
        "page": 0,
        "pageSize": page_size,
        "sortFields": ["marketCap"],
        "sortOrders": ["DESC"],
        "filter": [
            {
                "name": "exchange",
                "conditionOptions": [
                    {"type": "value", "value": "hsx"},
                    {"type": "value", "value": "hnx"},
                    {"type": "value", "value": "upcom"}
                ]
            },
            # Yêu cầu include các trường cơ bản & kỹ thuật
            {"name": "ttmPe", "conditionOptions": [{"type": "range", "min": -999999, "max": 999999}]},
            {"name": "ttmPb", "conditionOptions": [{"type": "range", "min": -999999, "max": 999999}]},
            {"name": "ttmRoe", "conditionOptions": [{"type": "range", "min": -999999, "max": 999999}]},
            {"name": "rsi", "conditionOptions": [{"type": "range", "min": -999999, "max": 999999}]},
        ]
    }

    req = urllib.request.Request(
        SCREENER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=SCREENER_HEADERS,
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))

    content = res.get("data", {}).get("content", [])
    logger.info("✅ Vietcap IQ API phản hồi: Đã tải thành công %d mã cổ phiếu!", len(content))
    return content


def crawl_deep_screener(db_path: str = "db/vesta_snapshot.duckdb") -> int:
    """Xử lý chuẩn hóa và lưu trữ bộ lọc chuyên sâu vào CSDL VESTA."""
    items = fetch_deep_screener_data()
    if not items:
        logger.warning("Không có dữ liệu trả về từ Vietcap IQ API.")
        return 0

    today = dt.date.today()
    now_ts = dt.datetime.now()

    rows: List[Dict[str, Any]] = []
    for item in items:
        sym = item.get("ticker")
        if not sym:
            continue

        ex = item.get("exchange", "").upper()
        if ex == "HSX":
            ex = "HOSE"

        p = item.get("marketPrice")
        ref = item.get("refPrice")
        ceil = item.get("ceiling")
        flr = item.get("floor")
        chg_pct = item.get("dailyPriceChangePercent")
        mkt_cap = item.get("marketCap")
        val = item.get("accumulatedValue")
        vol = item.get("accumulatedVolume")
        strength = item.get("stockStrength")

        rows.append({
            "symbol": sym.upper(),
            "snapshot_date": today,
            "exchange": ex,
            "price": float(p) if p is not None else None,
            "reference_price": float(ref) if ref is not None else None,
            "ceiling_price": float(ceil) if ceil is not None else None,
            "floor_price": float(flr) if flr is not None else None,
            "price_change_percent": float(chg_pct) if chg_pct is not None else None,
            "market_cap": float(mkt_cap) if mkt_cap is not None else None,
            "accumulated_value": float(val) if val is not None else None,
            "accumulated_volume": float(vol) if vol is not None else None,
            "stock_strength": float(strength) if strength is not None else None,
            "data_json": json.dumps(item, ensure_ascii=False),
            "source": "VIETCAP_IQ_DIRECT",
            "fetched_at": now_ts,
        })

    df = pd.DataFrame(rows)
    con = duckdb.connect(db_path, read_only=False)
    try:
        con.execute("INSERT OR REPLACE INTO core.market_screener_snapshot SELECT * FROM df;")
        con.execute("INSERT INTO staging.market_screener_snapshot SELECT * FROM df;")
        con.execute("CHECKPOINT;")
    finally:
        con.close()

    logger.info("🎉 HOÀN TẤT: Đã ghi nhận +%d mã vào core.market_screener_snapshot (%s) với ngày %s!", len(rows), db_path, today)
    return len(rows)


if __name__ == "__main__":
    for target in ["db/vesta_snapshot.duckdb", "db/vesta_backup.duckdb"]:
        if os.path.exists(target):
            crawl_deep_screener(target)
