import sys
sys.stdout.reconfigure(encoding="utf-8")
import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

con = duckdb.connect("db/test_db/vesta_test.duckdb", read_only=True)

# Check top liquid symbols per sector to build robust sector price series
query = """
WITH ranked_symbols AS (
    SELECT 
        s.industry_name,
        s.industry_code,
        p.symbol,
        count(*) as n_bars,
        avg(p.volume * p.close) as avg_trading_val
    FROM core.market_ohlcv_daily p
    JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.close > 0 AND p.date >= '2015-01-01' AND s.industry_name IS NOT NULL
    GROUP BY 1, 2, 3
    HAVING count(*) >= 1000
)
SELECT industry_name, count(DISTINCT symbol) as n_liquid_stocks, sum(avg_trading_val) as total_val
FROM ranked_symbols
GROUP BY 1
ORDER BY 3 DESC
"""
df_sectors = con.execute(query).df()
print("Liquid sectors summary:")
print(df_sectors.to_string())

# Check daily sector series construction
query_daily = """
WITH top_syms AS (
    SELECT 
        s.symbol,
        s.industry_name,
        ROW_NUMBER() OVER (PARTITION BY s.industry_name ORDER BY avg(p.volume * p.close) DESC) as rnk
    FROM core.market_ohlcv_daily p
    JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.close > 0 AND p.date >= '2018-01-01' AND s.industry_name IS NOT NULL
    GROUP BY s.symbol, s.industry_name
    HAVING count(*) >= 1200
)
SELECT 
    p.date,
    s.industry_name,
    avg(p.close) as avg_price,
    exp(avg(ln(p.close))) as geom_avg_price,
    count(DISTINCT p.symbol) as stocks_in_basket
FROM core.market_ohlcv_daily p
JOIN top_syms s ON p.symbol = s.symbol AND s.rnk <= 10
WHERE p.close > 0 AND p.date >= '2018-01-01'
GROUP BY 1, 2
ORDER BY 2, 1
"""
df_sec_ts = con.execute(query_daily).df()
print(f"\nTotal daily sector bars: {len(df_sec_ts):,}")
print(df_sec_ts.head(10).to_string())

con.close()
