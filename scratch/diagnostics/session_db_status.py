"""Comprehensive Database inspection and status summary tool for VESTA."""
import sys
import os
import pathlib

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    db_path = db.DB_PATH
    wal_path = db_path.parent / "vesta.duckdb.wal"

    print("==========================================================")
    print("               VESTA DATABASE STATUS                      ")
    print("==========================================================")
    print(f"DB Path: {db_path} ({os.path.getsize(db_path):,} bytes)" if os.path.exists(db_path) else "DB does not exist")
    print(f"WAL Path: {wal_path} ({os.path.getsize(wal_path):,} bytes)" if os.path.exists(wal_path) else "WAL: clean (merged)")

    con = db.connect(read_only=True)

    print("\n--- TABLE ROW COUNTS ---")
    tables = con.execute("""
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema IN ('core', 'staging', 'meta')
        ORDER BY table_schema, table_name
    """).fetchall()

    for s, t in tables:
        count = con.execute(f"SELECT count(*) FROM {s}.{t}").fetchone()[0]
        print(f"  {s}.{t}: {count:,} rows")

    print("\n--- META.CRAWL_PROGRESS BY DATASET & STATUS ---")
    prog_df = con.execute("""
        SELECT dataset_name, status, count(*) as count
        FROM meta.crawl_progress
        GROUP BY dataset_name, status
        ORDER BY dataset_name, status
    """).df()
    print(prog_df.to_string(index=False))

    print("\n--- SUMMARY OF COMPLETED FEATURES ---")
    total_symbols = con.execute("SELECT count(distinct symbol) FROM core.dim_symbol").fetchone()[0]
    ohlcv_symbols = con.execute("SELECT count(distinct symbol) FROM core.market_ohlcv_daily").fetchone()[0]
    news_symbols = con.execute("SELECT count(distinct symbol) FROM core.news").fetchone()[0]
    fund_symbols = con.execute("SELECT count(distinct symbol) FROM core.fundamentals").fetchone()[0]

    print(f"  [F001] Symbols Universe : {total_symbols:,} symbols")
    print(f"  [F002] OHLCV Daily      : {ohlcv_symbols:,} symbols ({ohlcv_symbols/total_symbols*100:.1f}%) | 2000 - 2026")
    print(f"  [F003/F004] News Feed   : {news_symbols:,} symbols ({news_symbols/total_symbols*100:.1f}%)")
    print(f"  [F005] Fundamentals     : {fund_symbols:,} symbols ({fund_symbols/total_symbols*100:.1f}%) | 2018 - 2026")
    print("==========================================================")

if __name__ == "__main__":
    main()
