"""src/crawlers/crawl_cafef_foreign_flow.py

Crawls foreign trading flow (Giao dịch khối ngoại) from CafeF API:
https://cafef.vn/du-lieu/Ajax/PageNew/DataGDNN/GDNuocNgoai.ashx?TradeCenter={center}&Date={DD/MM/YYYY}
Stores directly into core.market_foreign_flow_daily in db/vesta.duckdb.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_DB_PATH = "db/vesta_crawled_fresh.duckdb"
API_URL = "https://cafef.vn/du-lieu/Ajax/PageNew/DataGDNN/GDNuocNgoai.ashx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://cafef.vn/du-lieu/tracuulichsu2/3/hose/11/09/2026.chn",
    "Accept": "*/*"
}


def parse_cafef_date(date_str: str) -> Optional[datetime.date]:
    match = re.search(r"/Date\((\d+)\)/", str(date_str))
    if match:
        ts = int(match.group(1)) / 1000.0
        return datetime.datetime.fromtimestamp(ts).date()
    return None


def crawl_foreign_flow_date(date_obj: datetime.date, exchange: str = "HOSE", con: Optional[duckdb.DuckDBPyConnection] = None) -> int:
    """Crawls foreign trading flow for a single date and exchange."""
    date_str = date_obj.strftime("%d/%m/%Y")
    url = f"{API_URL}?TradeCenter={exchange}&Date={date_str}"
    
    close_con = False
    if con is None:
        con = duckdb.connect(CANONICAL_DB_PATH)
        close_con = True

    con.execute("""
    CREATE SCHEMA IF NOT EXISTS core;
    CREATE TABLE IF NOT EXISTS core.market_foreign_flow_daily (
        symbol        VARCHAR NOT NULL,
        date          DATE NOT NULL,
        buy_volume    DOUBLE,
        sell_volume   DOUBLE,
        net_volume    DOUBLE,
        foreign_room  DOUBLE,
        fetched_at    TIMESTAMP NOT NULL,
        PRIMARY KEY (symbol, date)
    );
    """)

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            items = payload.get("Data", {}).get("ListDataNN", [])
            if not items:
                return 0

            rows = []
            now = datetime.datetime.now()
            for it in items:
                sym = str(it.get("Symbol", "")).strip().upper()
                if not sym:
                    continue
                
                t_date = parse_cafef_date(it.get("TradeDate")) or date_obj
                rows.append({
                    "symbol": sym,
                    "date": t_date,
                    "buy_volume": float(it.get("BuyVolume", 0)),
                    "sell_volume": float(it.get("SellVolume", 0)),
                    "net_volume": float(it.get("NetVolume", 0)),
                    "foreign_room": float(it.get("Room", 0)),
                    "fetched_at": now
                })

            if rows:
                df = pd.DataFrame(rows).drop_duplicates(subset=["symbol", "date"])
                con.register("df_ff", df)
                con.execute("""
                INSERT INTO core.market_foreign_flow_daily (symbol, date, buy_volume, sell_volume, net_volume, foreign_room, fetched_at)
                SELECT symbol, date, buy_volume, sell_volume, net_volume, foreign_room, fetched_at FROM df_ff
                ON CONFLICT (symbol, date) DO UPDATE SET
                    buy_volume = EXCLUDED.buy_volume,
                    sell_volume = EXCLUDED.sell_volume,
                    net_volume = EXCLUDED.net_volume,
                    foreign_room = EXCLUDED.foreign_room,
                    fetched_at = EXCLUDED.fetched_at;
                """)
                return len(df)
    except Exception as e:
        print(f" -> Lỗi cào ngày {date_str} sàn {exchange}: {e}")
    finally:
        if close_con:
            con.close()
    return 0


def backfill_foreign_flow(start_date: datetime.date, end_date: datetime.date, exchanges=["HOSE", "HNX", "UPCOM"], delay=0.5):
    """Backfills foreign flow across a date range."""
    print("=" * 80)
    print(f"CÀO DÒNG TIỀN KHỐI NGOẠI: TỪ {start_date} ĐẾN {end_date} (SÀN: {exchanges})")
    print(f"Cơ sở dữ liệu: {CANONICAL_DB_PATH}")
    print("=" * 80)

    con = duckdb.connect(CANONICAL_DB_PATH)
    curr = start_date
    total_records = 0

    while curr <= end_date:
        # Bỏ qua thứ 7 và Chủ nhật
        if curr.weekday() < 5:
            for ex in exchanges:
                cnt = crawl_foreign_flow_date(curr, exchange=ex, con=con)
                if cnt > 0:
                    total_records += cnt
                    print(f" -> [{curr.strftime('%d/%m/%Y')}] Sàn {ex:<5}: Đã lưu {cnt:>3} mã cổ phiếu vào core.market_foreign_flow_daily.")
                time.sleep(delay)
        curr += datetime.timedelta(days=1)

    total_in_db = con.execute("SELECT count(*) FROM core.market_foreign_flow_daily").fetchone()[0]
    con.close()
    print(f"\n -> [HOÀN TẤT] Đã nạp thêm {total_records:,} bản ghi. Tổng số dòng trong DB: {total_in_db:,}")


if __name__ == "__main__":
    # Test cào ngày 11/09/2026 mà người dùng yêu cầu
    test_date = datetime.date(2026, 9, 11)
    backfill_foreign_flow(start_date=test_date, end_date=test_date, exchanges=["HOSE", "HNX", "UPCOM"])
