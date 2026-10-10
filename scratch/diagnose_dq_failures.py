import duckdb

# 1. Check ohlcv_daily bounds
con_ohlcv = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
bad_bounds = con_ohlcv.execute("""
    SELECT symbol, date, open, high, low, close, volume
    FROM core.market_ohlcv_daily
    WHERE high < low OR high < open OR high < close OR low > open OR low > close OR close <= 0 OR volume < 0
    LIMIT 10
""").fetchall()
cnt_bad_bounds = con_ohlcv.execute("""
    SELECT COUNT(*)
    FROM core.market_ohlcv_daily
    WHERE high < low OR high < open OR high < close OR low > open OR low > close OR close <= 0 OR volume < 0
""").fetchone()[0]
print(f"1. OHLCV bad bounds count: {cnt_bad_bounds}")
for b in bad_bounds[:5]:
    print("  ", b)
con_ohlcv.close()

# 2. Check fear_greed range
con_mkt = duckdb.connect('db/vesta_market_index.duckdb', read_only=True)
bad_fg = con_mkt.execute("""
    SELECT exchange, snapshot_date, fear_greed_score
    FROM core.market_sentiment_snapshot
    WHERE fear_greed_score < 0 OR fear_greed_score > 100
    LIMIT 5
""").fetchall()
print(f"\n2. Bad Fear & Greed rows ({len(bad_fg)}):")
for f in bad_fg:
    print("  ", f)
con_mkt.close()

# 3. Check fundamentals period_end
con_fun = duckdb.connect('db/vesta_fundamentals.duckdb', read_only=True)
bad_fun = con_fun.execute("""
    SELECT symbol, report_type, period_end
    FROM core.fundamentals
    WHERE period_end < '2000-01-01' OR period_end > '2026-12-31'
    LIMIT 5
""").fetchall()
cnt_bad_fun = con_fun.execute("""
    SELECT COUNT(*)
    FROM core.fundamentals
    WHERE period_end < '2000-01-01' OR period_end > '2026-12-31'
""").fetchone()[0]
print(f"\n3. Bad fundamentals period_end count: {cnt_bad_fun}")
for f in bad_fun:
    print("  ", f)
con_fun.close()
