import duckdb
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

for target_db in ['db/vesta_snapshot.duckdb', 'db/vesta_backup.duckdb']:
    if not os.path.exists(target_db):
        continue
    print(f"\n=== BACKFILL HISTORICAL MARKET SENTIMENT -> {target_db} ===")
    con = duckdb.connect(target_db, read_only=False)
    con.execute("ATTACH 'db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
    
    insert_sql = """
    INSERT OR REPLACE INTO core.market_sentiment_snapshot
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
    """
    
    con.execute(insert_sql)
    con.execute("CHECKPOINT;")
    
    count_now = con.execute("SELECT count(*) FROM core.market_sentiment_snapshot").fetchone()[0]
    min_date = con.execute("SELECT min(snapshot_date) FROM core.market_sentiment_snapshot").fetchone()[0]
    max_date = con.execute("SELECT max(snapshot_date) FROM core.market_sentiment_snapshot").fetchone()[0]
    print(f"✅ Hoàn tất! Số dòng trong core.market_sentiment_snapshot: {count_now:,} dòng")
    print(f"📅 Phạm vi thời gian: {min_date} đến {max_date}")
    
    sample_df = con.execute("""
        SELECT exchange, snapshot_date, fear_greed_score, advances, declines, no_change, source
        FROM core.market_sentiment_snapshot
        ORDER BY snapshot_date DESC, exchange
        LIMIT 6
    """).df()
    print("Mẫu dữ liệu mới nhất:")
    print(sample_df)
    
    con.close()
