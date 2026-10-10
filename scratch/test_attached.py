import duckdb

con = duckdb.connect('d:/VESTA/db/vesta_ohlcv.duckdb', read_only=True)
con.execute("ATTACH 'd:/VESTA/db/vesta_market_index.duckdb' AS market_index (READ_ONLY)")
con.execute("ATTACH 'd:/VESTA/db/vesta_events.duckdb' AS events (READ_ONLY)")
con.execute("ATTACH 'd:/VESTA/db/vesta_news.duckdb' AS news_db (READ_ONLY)")
con.execute("ATTACH 'd:/VESTA/db/vesta_fundamentals.duckdb' AS fundamentals (READ_ONLY)")

# 1. Foreign net flow
ff = con.execute("SELECT date, buy_value/1e9, sell_value/1e9, net_value/1e9 FROM market_index.core.market_foreign_flow_daily ORDER BY date DESC LIMIT 5").fetchall()
print('Foreign flow top 5 (billion VND):', ff)

# 2. Market breadth
br = con.execute("SELECT date, advancing, declining, unchanged, ratio_advance_decline, pct_above_ma20 FROM market_index.core.market_breadth_series ORDER BY date DESC LIMIT 5").fetchall()
print('Breadth top 5:', br)

# 3. Market sentiment
sent = con.execute("SELECT date, sentiment_score, fear_greed_score, sentiment_label FROM market_index.core.market_sentiment_snapshot ORDER BY date DESC LIMIT 5").fetchall()
print('Sentiment top 5:', sent)

# 4. Total turnover on 2026-10-09
# Let's check close price in core.market_ohlcv_daily
val = con.execute("""
    SELECT 
        COUNT(CASE WHEN close > open THEN 1 END) as advancing,
        COUNT(CASE WHEN close < open THEN 1 END) as declining,
        COUNT(CASE WHEN close = open THEN 1 END) as unchanged,
        COUNT(CASE WHEN close >= open * 1.069 THEN 1 END) as ceiling,
        COUNT(CASE WHEN close <= open * 0.931 THEN 1 END) as floor,
        COALESCE(SUM(volume * close * 1000) / 1e9, 0.0) as total_val_bil,
        COALESCE(SUM(volume) / 1e6, 0.0) as total_vol_mil
    FROM core.market_ohlcv_daily
    WHERE date = '2026-10-09'
""").fetchone()
print('Market summary calculation on 2026-10-09:', val)
