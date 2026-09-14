"""src/crawlers/merge_fresh_into_canonical.py

Merges all newly crawled data from db/vesta_crawled_fresh.duckdb into db/vesta.duckdb.
Safely executed when no other process is holding a write lock.
"""
from __future__ import annotations

import os
import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_DB = "db/vesta.duckdb"
FRESH_DB = "db/vesta_crawled_fresh.duckdb"


def merge_databases():
    if not os.path.exists(FRESH_DB):
        print(f"Không tìm thấy database {FRESH_DB}. Chưa có dữ liệu mới để đồng bộ.")
        return

    print("=" * 80)
    print("ĐỒNG BỘ DỮ LIỆU TỪ vesta_crawled_fresh.duckdb VÀO vesta.duckdb")
    print("=" * 80)

    try:
        con = duckdb.connect(CANONICAL_DB)
    except Exception as e:
        print(f"LỖI KHÓA TIẾN TRÌNH: {e}")
        print("Vui lòng đợi hoặc tắt terminal đang cào dữ liệu trước khi chạy lệnh merge này!")
        return

    # Attach fresh db
    con.execute(f"ATTACH '{FRESH_DB}' AS fresh;")

    # 1. Merge disclosures
    tables = [t[0] for t in con.execute("SHOW TABLES FROM fresh").fetchall()]
    print("Các bảng có dữ liệu mới trong database tạm:", tables)

    if "cafef_disclosures" in tables:
        cnt_before = con.execute("SELECT count(*) FROM core.cafef_disclosures").fetchone()[0]
        con.execute("""
        INSERT INTO core.cafef_disclosures 
        SELECT * FROM fresh.cafef_disclosures 
        ON CONFLICT (doc_id) DO NOTHING;
        """)
        cnt_after = con.execute("SELECT count(*) FROM core.cafef_disclosures").fetchone()[0]
        print(f" -> core.cafef_disclosures: Đã nạp thêm +{cnt_after - cnt_before:,} bản ghi (Tổng DB: {cnt_after:,}).")

    if "market_ohlcv_1m" in tables:
        cnt_before = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
        con.execute("""
        INSERT INTO core.market_ohlcv_1m 
        SELECT * FROM fresh.market_ohlcv_1m 
        ON CONFLICT (symbol, time) DO NOTHING;
        """)
        cnt_after = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
        print(f" -> core.market_ohlcv_1m: Đã nạp thêm +{cnt_after - cnt_before:,} nến 1m (Tổng DB: {cnt_after:,}).")

    if "market_foreign_flow_daily" in tables:
        cnt_before = con.execute("SELECT count(*) FROM core.market_foreign_flow_daily").fetchone()[0]
        con.execute("""
        INSERT INTO core.market_foreign_flow_daily (symbol, date, buy_volume, sell_volume, net_volume, foreign_room, fetched_at)
        SELECT symbol, date, buy_volume, sell_volume, net_volume, foreign_room, fetched_at FROM fresh.core.market_foreign_flow_daily
        ON CONFLICT (symbol, date) DO UPDATE SET
            buy_volume = EXCLUDED.buy_volume,
            sell_volume = EXCLUDED.sell_volume,
            net_volume = EXCLUDED.net_volume,
            foreign_room = EXCLUDED.foreign_room,
            fetched_at = EXCLUDED.fetched_at;
        """)
        cnt_after = con.execute("SELECT count(*) FROM core.market_foreign_flow_daily").fetchone()[0]
        print(f" -> core.market_foreign_flow_daily: Đã nạp thêm +{cnt_after - cnt_before:,} bản ghi (Tổng DB: {cnt_after:,}).")

    con.execute("DETACH fresh;")
    con.close()
    print("\n" + "=" * 80)
    print("ĐỒNG BỘ THÀNH CÔNG VÀO MAIN DATABASE db/vesta.duckdb!")
    print("=" * 80)


if __name__ == "__main__":
    merge_databases()
