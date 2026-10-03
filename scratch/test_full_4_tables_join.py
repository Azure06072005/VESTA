import duckdb
import pandas as pd
import numpy as np
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

print("Checking join between f104_train.parquet and the 4 tables...")
sample_df = pd.read_parquet('data/processed/f104/f104_train.parquet')
print(f"Total train rows: {len(sample_df):,}")

# Register sample_df into duckdb
con.register('df_train', sample_df.head(5000))

t0 = time.time()
q = """
WITH foreign_flow_summary AS (
    SELECT 
        symbol,
        date,
        net_value,
        SUM(net_value) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) as foreign_net_val_5d,
        SUM(net_value) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as foreign_net_val_20d,
        foreign_room
    FROM core.market_foreign_flow_daily
),
corp_events_summary AS (
    SELECT 
        symbol,
        event_date,
        COALESCE(payout_delay_days, 0) as payout_delay_days
    FROM core.corporate_events
),
breadth_summary AS (
    SELECT 
        exchange,
        trade_date,
        above_ma20_pct,
        above_ma50_pct
    FROM core.market_breadth_series
),
shareholder_summary AS (
    SELECT 
        symbol,
        SUM(ownership_percentage) as major_ownership_pct,
        COUNT(*) as num_major_shareholders
    FROM core.company_shareholders
    GROUP BY symbol
)
SELECT 
    t.symbol,
    t.event_date,
    t.target_dir_t5,
    -- 1st Priority: Foreign flow
    COALESCE(f.foreign_net_val_5d, 0.0) as foreign_net_val_5d,
    COALESCE(f.foreign_net_val_20d, 0.0) as foreign_net_val_20d,
    COALESCE(f.foreign_room, 0.0) as foreign_room,
    -- 2nd Priority: Corporate events
    COALESCE(e.payout_delay_days, 0) as payout_delay_days,
    -- 3rd Priority: Market Breadth
    COALESCE(b.above_ma20_pct, 0.5) as breadth_above_ma20_pct,
    COALESCE(b.above_ma50_pct, 0.5) as breadth_above_ma50_pct,
    -- 4th Priority: Shareholders
    COALESCE(s.major_ownership_pct, 0.0) as major_ownership_pct,
    COALESCE(s.num_major_shareholders, 0) as num_major_shareholders
FROM df_train t
ASOF LEFT JOIN foreign_flow_summary f
    ON t.symbol = f.symbol AND t.event_date >= f.date
ASOF LEFT JOIN corp_events_summary e
    ON t.symbol = e.symbol AND t.event_date >= e.event_date
ASOF LEFT JOIN breadth_summary b
    ON t.exchange = b.exchange AND t.event_date >= b.trade_date
LEFT JOIN shareholder_summary s
    ON t.symbol = s.symbol
"""
res = con.execute(q).df()
elapsed = time.time() - t0
print(f"Join completed in {elapsed:.2f}s! Extracted {len(res):,} enriched rows.")
print(res.head())
print("\nMissing values check:")
print(res.isnull().sum())
con.close()
