"""src/crawlers/crawl_all_symbols_1m.py

High-Resolution 1-Minute OHLCV Crawler for All Symbols using vnstock_data (Silver Tier).
Features:
1. Queries symbols from core.dim_symbol (HOSE, HNX, UPCOM).
2. Checkpoints progress in meta.crawl_progress (resumable if interrupted).
3. Inserts deduplicated bars into core.market_ohlcv_1m in db/vesta.duckdb.
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
DATASET_NAME = "ohlcv_1m"


def init_1m_table(con: duckdb.DuckDBPyConnection):
    con.execute("""
    CREATE SCHEMA IF NOT EXISTS core;
    CREATE SCHEMA IF NOT EXISTS meta;

    CREATE TABLE IF NOT EXISTS meta.crawl_progress (
        dataset_name  VARCHAR NOT NULL,
        symbol        VARCHAR NOT NULL,
        status        VARCHAR NOT NULL,
        retry_count   INTEGER NOT NULL DEFAULT 0,
        last_attempt  TIMESTAMP,
        PRIMARY KEY (dataset_name, symbol)
    );

    CREATE TABLE IF NOT EXISTS core.market_ohlcv_1m (
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
    """)


def get_symbols_to_crawl(con: duckdb.DuckDBPyConnection, exchange_filter: Optional[str] = None, resume: bool = True) -> List[str]:
    """Gets list of symbols, optionally skipping already completed ones."""
    query = "SELECT symbol FROM core.dim_symbol WHERE is_delisted = false"
    if exchange_filter:
        query += f" AND exchange = '{exchange_filter.upper()}'"
    
    all_syms = [r[0] for r in con.execute(query).fetchall()]

    if resume:
        completed = set(r[0] for r in con.execute(f"SELECT symbol FROM meta.crawl_progress WHERE dataset_name = '{DATASET_NAME}' AND status = 'success'").fetchall())
        pending_syms = [s for s in all_syms if s not in completed]
        print(f" -> Tổng số mã: {len(all_syms):,} | Đã hoàn thành trước đó: {len(completed):,} | Còn lại cần cào: {len(pending_syms):,}")
        return pending_syms
    return all_syms


def update_crawl_status(con: duckdb.DuckDBPyConnection, symbol: str, status: str):
    now = datetime.datetime.now()
    con.execute(f"""
    INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
    VALUES ('{DATASET_NAME}', '{symbol}', '{status}', 0, '{now}')
    ON CONFLICT (dataset_name, symbol) DO UPDATE SET
        status = EXCLUDED.status,
        last_attempt = EXCLUDED.last_attempt;
    """)


def crawl_symbols_1m(limit: Optional[int] = None, exchange: Optional[str] = None, length: str = "1M", delay: float = 0.5):
    try:
        from vnstock_data import Market
        mkt = Market()
    except ImportError:
        print("Lỗi: Không tìm thấy thư viện vnstock_data. Hãy chạy với môi trường ảo chứa vnstock!")
        print("Ví dụ: d:\\vnstock\\.venv\\Scripts\\python.exe src/crawlers/crawl_all_symbols_1m.py")
        sys.exit(1)

    print("=" * 85)
    print(f"CÀO NẾN CAO TẦN 1 PHÚT (1m) TOÀN THỊ TRƯỜNG — VNSTOCK SILVER")
    print(f"Cơ sở dữ liệu: {CANONICAL_DB_PATH} | Độ dài: {length}")
    print("=" * 85)

    con = duckdb.connect(CANONICAL_DB_PATH)
    init_1m_table(con)

    symbols = get_symbols_to_crawl(con, exchange_filter=exchange, resume=True)
    if limit:
        symbols = symbols[:limit]
        print(f" -> Giới hạn cào: {limit} mã đầu tiên.")

    total_bars_crawled = 0
    success_count = 0
    failed_count = 0

    for idx, sym in enumerate(symbols, 1):
        print(f"[{idx}/{len(symbols)}] Đang cào mã {sym}...", end=" ", flush=True)
        try:
            df = mkt.equity(sym).ohlcv(length=length, interval="1m")
            if df is not None and not df.empty:
                df['symbol'] = sym
                df['time'] = pd.to_datetime(df['time'])
                df['fetched_at'] = datetime.datetime.now()

                req_cols = ['symbol', 'time', 'open', 'high', 'low', 'close', 'volume', 'fetched_at']
                df_clean = df[req_cols].dropna(subset=['time'])

                con.register("df_clean", df_clean)
                con.execute("""
                INSERT INTO core.market_ohlcv_1m 
                SELECT * FROM df_clean 
                ON CONFLICT (symbol, time) DO NOTHING;
                """)

                bars_cnt = len(df_clean)
                total_bars_crawled += bars_cnt
                success_count += 1
                update_crawl_status(con, sym, "success")
                print(f"Thành công! (+{bars_cnt:,} nến)")
            else:
                update_crawl_status(con, sym, "empty")
                print("Rỗng (0 nến).")
        except Exception as e:
            failed_count += 1
            update_crawl_status(con, sym, "failed")
            print(f"Thất bại: {e}")

        time.sleep(delay)

    total_in_db = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    con.close()

    print("\n" + "=" * 85)
    print("TỔNG KẾT PHIÊN CÀO NẾN 1 PHÚT:")
    print(f" - Số mã thành công   : {success_count:,}")
    print(f" - Số mã thất bại/rỗng: {failed_count:,}")
    print(f" - Tổng nến nạp mới   : {total_bars_crawled:,}")
    print(f" - Tổng nến trong DB  : {total_in_db:,}")
    print("=" * 85)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cào nến 1m toàn thị trường")
    parser.add_argument("--all", action="store_true", help="Cào tất cả các mã")
    parser.add_argument("--limit", type=int, default=10, help="Số lượng mã giới hạn cào (mặc định: 10)")
    parser.add_argument("--exchange", type=str, default=None, help="Lọc sàn: HOSE, HNX, hoặc UPCOM")
    parser.add_argument("--length", type=str, default="1M", help="Độ dài lịch sử: 1M, 3M, 6M, 1Y")
    parser.add_argument("--delay", type=float, default=0.5, help="Độ trễ giữa các mã (giây)")
    args = parser.parse_args()

    limit = None if args.all else args.limit
    crawl_symbols_1m(limit=limit, exchange=args.exchange, length=args.length, delay=args.delay)
