import duckdb
import time

con = duckdb.connect("db/vesta_test.duckdb", read_only=True)

t0 = time.time()
print("Benchmarking Vectorized Momentum & Volatility calculation on vesta_test.duckdb...")

# 2-step CTE to avoid nested window functions
query = """
WITH daily_returns AS (
    SELECT 
        symbol,
        date,
        close,
        CASE WHEN LAG(close, 1) OVER w > 0 THEN (close - LAG(close, 1) OVER w) / LAG(close, 1) OVER w ELSE NULL END AS ret_1d,
        CASE WHEN LAG(close, 5) OVER w > 0 THEN (close - LAG(close, 5) OVER w) / LAG(close, 5) OVER w ELSE NULL END AS mom_5d,
        CASE WHEN LAG(close, 20) OVER w > 0 THEN (close - LAG(close, 20) OVER w) / LAG(close, 20) OVER w ELSE NULL END AS mom_20d
    FROM core.market_ohlcv_daily
    WHERE close > 0
    WINDOW w AS (PARTITION BY symbol ORDER BY date)
),
daily_stats AS (
    SELECT 
        symbol,
        date,
        close,
        ret_1d AS mom_1d,
        mom_5d,
        mom_20d,
        STDDEV_SAMP(ret_1d) OVER (
            PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS vol_20d
    FROM daily_returns
),
events AS (
    SELECT 
        symbol,
        source_url,
        published_at,
        CAST(published_at AS DATE) AS effective_date,
        headline,
        price_at_publish,
        price_t1,
        price_t5,
        price_t30,
        fundamentals_json
    FROM core.pit_events
    LIMIT 20000
)
SELECT 
    e.symbol,
    e.published_at,
    e.effective_date,
    e.headline,
    e.price_at_publish,
    e.price_t1,
    e.price_t5,
    e.price_t30,
    e.fundamentals_json,
    s.mom_1d,
    s.mom_5d,
    s.mom_20d,
    s.vol_20d
FROM events e
ASOF JOIN daily_stats s
  ON e.symbol = s.symbol AND e.effective_date >= s.date
"""

df = con.execute(query).df()
elapsed = time.time() - t0
print(f"Computed {len(df):,} events with full momentum and volatility in {elapsed:.2f} seconds!")
print(f"Throughput: {len(df) / elapsed:.0f} events/second")
print("Sample output:")
print(df[["symbol", "effective_date", "mom_1d", "mom_5d", "mom_20d", "vol_20d"]].head())

con.close()
