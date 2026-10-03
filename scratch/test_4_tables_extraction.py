import duckdb
import pandas as pd
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

print("=== TESTING EXTRACTION FROM 4 TABLES IN DUCKDB ===")

# 1. Foreign Flow test
t0 = time.time()
q_foreign = """
WITH ranked_flow AS (
    SELECT 
        symbol,
        date,
        net_value,
        SUM(net_value) OVER (
            PARTITION BY symbol 
            ORDER BY date 
            ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ) as foreign_net_val_5d,
        SUM(net_value) OVER (
            PARTITION BY symbol 
            ORDER BY date 
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) as foreign_net_val_20d,
        foreign_room
    FROM core.market_foreign_flow_daily
)
SELECT * FROM ranked_flow WHERE symbol = 'VCB' ORDER BY date DESC LIMIT 5
"""
df_f = con.execute(q_foreign).df()
print(f"1. Foreign Flow calculated in {time.time() - t0:.2f}s:")
print(df_f)

# 2. Corporate Events test
t0 = time.time()
q_events = """
SELECT 
    symbol,
    event_date,
    event_type,
    payout_delay_days
FROM core.corporate_events
WHERE symbol = 'VCB'
ORDER BY event_date DESC LIMIT 5
"""
df_e = con.execute(q_events).df()
print(f"\n2. Corporate Events sample in {time.time() - t0:.2f}s:")
print(df_e)

# 3. Market Breadth test
t0 = time.time()
q_breadth = """
SELECT 
    exchange,
    trade_date,
    above_ma20_pct,
    above_ma50_pct,
    above_ma200_pct
FROM core.market_breadth_series
ORDER BY trade_date DESC LIMIT 5
"""
df_b = con.execute(q_breadth).df()
print(f"\n3. Market Breadth sample in {time.time() - t0:.2f}s:")
print(df_b)

# 4. Shareholders test
t0 = time.time()
q_shareholders = """
SELECT 
    symbol,
    SUM(ownership_percentage) as total_major_pct,
    COUNT(*) as num_major_shareholders
FROM core.company_shareholders
GROUP BY symbol
LIMIT 5
"""
df_s = con.execute(q_shareholders).df()
print(f"\n4. Shareholders aggregated in {time.time() - t0:.2f}s:")
print(df_s)

con.close()
