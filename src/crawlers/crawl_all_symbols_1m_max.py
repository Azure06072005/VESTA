"""src/crawlers/crawl_all_symbols_1m_max.py

High-Resolution 1-Minute OHLCV Crawler for ALL Symbols with MAX HISTORICAL DATES (length='1Y', up to 21,236 bars/symbol).
Saves directly into the DEDICATED database (db/vesta_crawled_fresh.duckdb) to avoid file lock conflicts with running processes.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from typing import List, Optional

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_DB_PATH = "db/vesta.duckdb"
FRESH_DB_PATH = "db/vesta_crawled_fresh.duckdb"
DATASET_NAME = "ohlcv_1m_max"


def init_tables(con: duckdb.DuckDBPyConnection):
    con.execute("""
    CREATE TABLE IF NOT EXISTS market_ohlcv_1m (
        symbol     VARCHAR NOT NULL,
        time       TIMESTAMP NOT NULL,
        open       DOUBLE,
        high       DOUBLE,
        low        DOUBLE,
        close      DOUBLE,
        volume     BIGINT,
        fetched_at TIMESTAMP NOT NULL,
        PRIMARY KEY (symbol, time)
    );

    CREATE TABLE IF NOT EXISTS crawl_progress (
        dataset_name  VARCHAR NOT NULL,
        symbol        VARCHAR NOT NULL,
        status        VARCHAR NOT NULL,
        bars_count    INTEGER NOT NULL DEFAULT 0,
        updated_at    TIMESTAMP NOT NULL,
        PRIMARY KEY (dataset_name, symbol)
    );
    """)


def get_symbols(exchange: Optional[str] = None) -> List[str]:
    """Reads symbol list from canonical DB using read_only=True (never locks)."""
    try:
        con = duckdb.connect(CANONICAL_DB_PATH, read_only=True)
        query = "SELECT symbol FROM core.dim_symbol WHERE is_delisted = false"
        if exchange:
            query += f" AND exchange = '{exchange.upper()}'"
        query += " ORDER BY symbol ASC"
        symbols = [r[0] for r in con.execute(query).fetchall()]
        con.close()
        return symbols
    except Exception as e:
        print(f"Không thể đọc danh sách mã từ {CANONICAL_DB_PATH}: {e}")
        return ["FPT", "HPG", "VCB", "MWG", "SSI", "VHM", "VIC", "TCB", "MBB", "STB"]


def crawl_all_symbols_1m_max(exchange: Optional[str] = None, limit: Optional[int] = None, delay: float = 0.5):
    try:
        from vnstock_data import Market
        mkt = Market()
    except ImportError:
        print("Lỗi: Cần chạy bằng môi trường ảo có vnstock_data!")
        print("Lệnh: d:\\vnstock\\.venv\\Scripts\\python.exe src/crawlers/crawl_all_symbols_1m_max.py")
        sys.exit(1)

    print("=" * 85)
    print("CÀO NẾN 1 PHÚT TOÀN BỘ NGÀY (MAX HISTORICAL DATES - 21,236 NẾN/MÃ)")
    print(f"Cơ sở dữ liệu độc lập: {FRESH_DB_PATH}")
    print(f"Khung thời gian: 1m | Độ dài truy vấn: length='1Y' (Vét cạn trần server)")
    print("=" * 85)

    con = duckdb.connect(FRESH_DB_PATH)
    init_tables(con)

    all_symbols = get_symbols(exchange)
    
    # Check completed symbols in fresh DB
    completed = set(r[0] for r in con.execute(f"SELECT symbol FROM crawl_progress WHERE dataset_name = '{DATASET_NAME}' AND status = 'success'").fetchall())
    pending_symbols = [s for s in all_symbols if s not in completed]

    print(f" -> Tổng số mã: {len(all_symbols):,} | Đã hoàn thành: {len(completed):,} | Còn lại cần cào: {len(pending_symbols):,}")

    if limit:
        pending_symbols = pending_symbols[:limit]
        print(f" -> Giới hạn phiên này: {limit} mã.")

    total_bars = 0
    now = datetime.datetime.now()

    for idx, sym in enumerate(pending_symbols, 1):
        print(f"[{idx:>4}/{len(pending_symbols):<4}] Cào mã {sym:<6}...", end=" ", flush=True)
        try:
            # length='1Y' captures max buffer (~21,236 1-minute bars)
            df = mkt.equity(sym).ohlcv(length="1Y", interval="1m")
            if df is not None and not df.empty:
                df['symbol'] = sym
                df['time'] = pd.to_datetime(df['time'])
                df['fetched_at'] = now

                req_cols = ['symbol', 'time', 'open', 'high', 'low', 'close', 'volume', 'fetched_at']
                df_clean = df[req_cols].dropna(subset=['time'])

                con.register("df_clean", df_clean)
                con.execute("INSERT INTO market_ohlcv_1m SELECT * FROM df_clean ON CONFLICT (symbol, time) DO NOTHING;")

                bars_cnt = len(df_clean)
                total_bars += bars_cnt
                
                con.execute(f"""
                INSERT INTO crawl_progress (dataset_name, symbol, status, bars_count, updated_at)
                VALUES ('{DATASET_NAME}', '{sym}', 'success', {bars_cnt}, '{datetime.datetime.now()}')
                ON CONFLICT (dataset_name, symbol) DO UPDATE SET
                    status = EXCLUDED.status,
                    bars_count = EXCLUDED.bars_count,
                    updated_at = EXCLUDED.updated_at;
                """)
                print(f"Thành công! (+{bars_cnt:,} nến) [Từ {df_clean['time'].min().strftime('%d/%m/%Y')} -> {df_clean['time'].max().strftime('%d/%m/%Y')}]")
            else:
                con.execute(f"""
                INSERT INTO crawl_progress (dataset_name, symbol, status, bars_count, updated_at)
                VALUES ('{DATASET_NAME}', '{sym}', 'empty', 0, '{datetime.datetime.now()}')
                ON CONFLICT (dataset_name, symbol) DO UPDATE SET status = 'empty', updated_at = EXCLUDED.updated_at;
                """)
                print("Rỗng (0 nến).")
        except Exception as e:
            con.execute(f"""
            INSERT INTO crawl_progress (dataset_name, symbol, status, bars_count, updated_at)
            VALUES ('{DATASET_NAME}', '{sym}', 'failed', 0, '{datetime.datetime.now()}')
            ON CONFLICT (dataset_name, symbol) DO UPDATE SET status = 'failed', updated_at = EXCLUDED.updated_at;
            """)
            print(f"Lỗi: {e}")

        time.sleep(delay)

    total_in_db = con.execute("SELECT count(*) FROM market_ohlcv_1m").fetchone()[0]
    con.close()

    print("\n" + "=" * 85)
    print(f"HOÀN TẤT PHIÊN CÀO NẾN 1M! Đã nạp {total_bars:,} nến mới vào {FRESH_DB_PATH} (Tổng DB: {total_in_db:,}).")
    print("=" * 85)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cào nến 1m max dates")
    parser.add_argument("--all", action="store_true", help="Cào toàn bộ mã còn lại")
    parser.add_argument("--limit", type=int, default=10, help="Giới hạn số mã (mặc định: 10)")
    parser.add_argument("--exchange", type=str, default=None, help="Lọc sàn: HOSE, HNX, UPCOM")
    parser.add_argument("--delay", type=float, default=0.5, help="Độ trễ giữa các mã (giây)")
    args = parser.parse_args()

    limit = None if args.all else args.limit
    crawl_all_symbols_1m_max(exchange=args.exchange, limit=limit, delay=args.delay)
