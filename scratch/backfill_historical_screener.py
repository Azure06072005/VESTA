import duckdb
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

print("=== BẮT ĐẦU TÁI TẠO LỊCH SỬ 21 NĂM (2005 - 2026) CHO MARKET_SCREENER_SNAPSHOT ===")
start_time = time.time()

backfill_sql = """
INSERT OR REPLACE INTO core.market_screener_snapshot
WITH ohlcv_at_period AS (
    SELECT 
        o.symbol,
        o.date,
        o.close as price,
        o.volume as accumulated_volume,
        o.close * o.volume as accumulated_value
    FROM ohlcv_db.core.market_ohlcv_daily o
)
SELECT 
    f.symbol,
    f.period_end as snapshot_date,
    coalesce(s.exchange, 'HOSE') as exchange,
    coalesce(p.price, f.pe_ratio * 1000.0, 10000.0) as price,
    coalesce(p.price, f.pe_ratio * 1000.0, 10000.0) as reference_price,
    coalesce(p.price, 10000.0) * 1.07 as ceiling_price,
    coalesce(p.price, 10000.0) * 0.93 as floor_price,
    0.0 as price_change_percent,
    coalesce(f.market_cap, p.price * coalesce(f.outstanding_shares, 10000000.0), 10000000000.0) as market_cap,
    coalesce(p.accumulated_value, 0.0) as accumulated_value,
    coalesce(p.accumulated_volume, 0.0) as accumulated_volume,
    50.0 as stock_strength,
    json_object(
        'pe', f.pe_ratio,
        'pb', f.pb_ratio,
        'ps', f.ps_ratio,
        'roe', f.roe,
        'roa', f.roa,
        'roic', f.roic,
        'gross_margin', f.gross_margin,
        'net_margin', f.net_margin,
        'debt_to_equity', f.debt_to_equity,
        'current_ratio', f.current_ratio,
        'quick_ratio', f.quick_ratio,
        'ev_ebitda', f.ev_ebitda,
        'dividend_yield', f.dividend_yield
    ) as data_json,
    'HISTORICAL_FACTOR_RECONSTRUCTED' as source,
    current_timestamp as fetched_at
FROM preprocessed.fundamentals_ratios f
LEFT JOIN core.dim_symbol s ON f.symbol = s.symbol
LEFT JOIN ohlcv_at_period p ON f.symbol = p.symbol AND f.period_end = p.date
WHERE f.period_end >= '2005-01-01';
"""

targets = ["db/vesta_snapshot.duckdb", "db/vesta_backup.duckdb"]

for target_db in targets:
    if not os.path.exists(target_db):
        continue
    print(f"\n-> Đang thực thi nạp dữ liệu vào {target_db}...")
    con = duckdb.connect(target_db, read_only=False)
    con.execute("ATTACH 'db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
    
    con.execute(backfill_sql)
    con.execute("CHECKPOINT;")
    
    total_cnt = con.execute("SELECT count(*) FROM core.market_screener_snapshot").fetchone()[0]
    min_d, max_d = con.execute("SELECT min(snapshot_date), max(snapshot_date) FROM core.market_screener_snapshot").fetchone()
    num_syms = con.execute("SELECT count(DISTINCT symbol) FROM core.market_screener_snapshot").fetchone()[0]
    
    print(f"🎉 Hoàn tất nạp vào {target_db}!")
    print(f"   • Tổng số bản ghi Screener: {total_cnt:,} dòng")
    print(f"   • Số lượng mã bao phủ      : {num_syms:,} mã")
    print(f"   • Chuỗi thời gian lịch sử  : {min_d} đến {max_d}")
    
    con.close()

print(f"\n✅ TOÀN BỘ TIẾN TRÌNH HOÀN THÀNH TRONG {time.time() - start_time:.2f} GIÂY!")
