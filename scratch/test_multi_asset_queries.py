import duckdb

ohlcv_con = duckdb.connect('d:/VESTA/db/vesta_ohlcv.duckdb', read_only=True)
mkt_con = duckdb.connect('d:/VESTA/db/vesta_market_index.duckdb', read_only=True)

# 1. Derivatives query
deriv_rows = ohlcv_con.execute("""
    WITH ranked AS (
        SELECT 
            symbol, date, open, high, low, close, volume, open_interest, basis,
            LAG(close) OVER (PARTITION BY symbol ORDER BY date ASC) as prev_close,
            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
        FROM core.market_derivatives_daily
    )
    SELECT symbol, date, close, ROUND(close - COALESCE(prev_close, close), 2) as chg,
           ROUND((close - COALESCE(prev_close, close)) / NULLIF(COALESCE(prev_close, close), 0) * 100.0, 2) as pct_change,
           volume, open_interest, basis
    FROM ranked WHERE rn = 1
    ORDER BY volume DESC
""").fetchall()
print("Derivatives on 2026-10-09:")
for r in deriv_rows:
    print(" ", r)

# 2. ETF query (top ETFs by trading volume on 2026-10-09)
etf_rows = ohlcv_con.execute("""
    WITH ranked AS (
        SELECT 
            symbol, date, open, high, low, close, volume,
            LAG(close) OVER (PARTITION BY symbol ORDER BY date ASC) as prev_close,
            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
        FROM core.market_etf_daily
    )
    SELECT symbol, date, close, ROUND(close - COALESCE(prev_close, close), 2) as chg,
           ROUND((close - COALESCE(prev_close, close)) / NULLIF(COALESCE(prev_close, close), 0) * 100.0, 2) as pct_change,
           volume
    FROM ranked WHERE rn = 1
    ORDER BY volume DESC LIMIT 8
""").fetchall()
print("\nTop ETFs on 2026-10-09:")
for r in etf_rows:
    print(" ", r)

# 3. CW query (top CWs by trading volume on 2026-10-09)
cw_rows = ohlcv_con.execute("""
    WITH ranked AS (
        SELECT 
            symbol, date, close, volume, underlying_symbol,
            LAG(close) OVER (PARTITION BY symbol ORDER BY date ASC) as prev_close,
            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
        FROM core.market_covered_warrants_daily
    )
    SELECT symbol, underlying_symbol, date, close, ROUND(close - COALESCE(prev_close, close), 2) as chg,
           ROUND((close - COALESCE(prev_close, close)) / NULLIF(COALESCE(prev_close, close), 0) * 100.0, 2) as pct_change,
           volume
    FROM ranked WHERE rn = 1
    ORDER BY volume DESC LIMIT 8
""").fetchall()
print("\nTop CWs on 2026-10-09:")
for r in cw_rows:
    print(" ", r)

# 4. Foreign flow query (grouped by date)
ff_rows = mkt_con.execute("""
    SELECT 
        date, 
        ROUND(SUM(buy_value) / 1e9, 1) as buy_bil,
        ROUND(SUM(sell_value) / 1e9, 1) as sell_bil,
        ROUND(SUM(net_value) / 1e9, 1) as net_bil
    FROM core.market_foreign_flow_daily
    GROUP BY date
    ORDER BY date DESC
    LIMIT 10
""").fetchall()
print("\nForeign flow past 10 sessions:")
for r in ff_rows:
    print(" ", r)

ohlcv_con.close()
mkt_con.close()
