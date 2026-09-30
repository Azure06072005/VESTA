import duckdb
import pandas as pd
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)

print("=== 1. Summary of core.market_index_daily in vesta_ohlcv.duckdb ===")
df_idx = con.execute("""
    SELECT index_code, min(date) as min_date, max(date) as max_date, 
           count(*) as total_bars, 
           round(avg(close), 2) as avg_close, 
           round(avg(volume), 0) as avg_volume
    FROM core.market_index_daily
    WHERE index_code IN ('VNINDEX', 'VN30', 'HNX-INDEX', 'HNX30', 'UPCOM-INDEX', 'VN100')
    GROUP BY index_code
    ORDER BY index_code
""").fetchdf()
print(df_idx.to_string())

print("\n=== 2. Summary of Foreign Room & Sector ETF Baskets in core.market_ohlcv_daily ===")
etfs = ['FUEVFVND', 'FUESSVFL', 'E1VFVN30', 'FUEVN100']
df_etf = con.execute(f"""
    SELECT symbol, min(date) as min_date, max(date) as max_date, 
           count(*) as total_bars, 
           round(avg(close), 2) as avg_close, 
           round(avg(volume), 0) as avg_volume
    FROM core.market_ohlcv_daily
    WHERE symbol IN ({','.join([repr(x) for x in etfs])})
    GROUP BY symbol
    ORDER BY symbol
""").fetchdf()
print(df_etf.to_string())

print("\n=== 3. Correlation between VNINDEX, VN30, HNX-INDEX and VNDIAMOND (FUEVFVND) ===")
# Pivot dữ liệu để tính correlation từ 2021 đến 2026
query_corr = """
    WITH idx AS (
        SELECT date, close as vnindex_close
        FROM core.market_index_daily
        WHERE index_code = 'VNINDEX' AND date >= '2021-01-01'
    ),
    v30 AS (
        SELECT date, close as vn30_close
        FROM core.market_index_daily
        WHERE index_code = 'VN30' AND date >= '2021-01-01'
    ),
    hnx AS (
        SELECT date, close as hnx_close
        FROM core.market_index_daily
        WHERE index_code = 'HNX-INDEX' AND date >= '2021-01-01'
    ),
    diamond AS (
        SELECT date, close as diamond_close
        FROM core.market_ohlcv_daily
        WHERE symbol = 'FUEVFVND' AND date >= '2021-01-01'
    )
    SELECT i.date, i.vnindex_close, v.vn30_close, h.hnx_close, d.diamond_close
    FROM idx i
    LEFT JOIN v30 v ON i.date = v.date
    LEFT JOIN hnx h ON i.date = h.date
    LEFT JOIN diamond d ON i.date = d.date
    ORDER BY i.date ASC
"""
df_merged = con.execute(query_corr).fetchdf()
print(f"Merged series shape: {df_merged.shape}")
print("Correlation matrix (Daily Returns):")
returns = df_merged[['vnindex_close', 'vn30_close', 'hnx_close', 'diamond_close']].pct_change().dropna()
print(returns.corr().round(4).to_string())

con.close()
