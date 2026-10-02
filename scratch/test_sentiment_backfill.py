import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=False)
con.execute("ATTACH 'db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")

test_query = """
WITH symbol_ex AS (
    SELECT symbol, exchange
    FROM core.dim_symbol
    WHERE exchange IN ('HOSE', 'HNX', 'UPCOM')
),
ohlcv_lag AS (
    SELECT 
        o.symbol,
        e.exchange,
        o.date as snapshot_date,
        o.close,
        lag(o.close) OVER (PARTITION BY o.symbol ORDER BY o.date) as prev_close
    FROM ohlcv_db.core.market_ohlcv_daily o
    JOIN symbol_ex e ON o.symbol = e.symbol
    WHERE o.date >= '2000-01-01'
),
breadth AS (
    SELECT 
        exchange,
        snapshot_date,
        count(CASE WHEN close > prev_close THEN 1 END) as advances,
        count(CASE WHEN close < prev_close THEN 1 END) as declines,
        count(CASE WHEN close = prev_close THEN 1 END) as no_change
    FROM ohlcv_lag
    WHERE prev_close IS NOT NULL
    GROUP BY exchange, snapshot_date
)
SELECT 
    exchange,
    snapshot_date,
    round((advances - declines) * 100.0 / nullif(advances + declines + no_change, 0), 2) as fear_greed_score,
    advances,
    declines,
    no_change,
    NULL::DOUBLE as mfi,
    NULL::DOUBLE as rsi,
    NULL::DOUBLE as index_change,
    NULL::DOUBLE as volume_change,
    NULL::VARCHAR as raw_json,
    'HISTORICAL_OHLCV_RECONSTRUCTED' as source,
    current_timestamp as fetched_at
FROM breadth
ORDER BY snapshot_date DESC, exchange
LIMIT 10;
"""

df_sample = con.execute(test_query).df()
print("=== SAMPLE RECONSTRUCTED MARKET SENTIMENT (Top 10) ===")
print(df_sample)

# Đếm tổng số phiên sẽ được backfill
total_reconstructed = con.execute(f"SELECT count(*) FROM ({test_query.replace('LIMIT 10;', '')})").fetchone()[0]
print(f"\nTổng số phiên có thể tái tạo cho cả 3 sàn: {total_reconstructed:,} phiên!")

con.close()
