import duckdb
import json
import urllib.request

con = duckdb.connect('d:/VESTA/db/vesta_ohlcv.duckdb', read_only=True)
r = con.execute("SELECT AVG(close), MIN(close), MAX(close) FROM core.market_ohlcv_daily WHERE date = '2026-10-09'").fetchone()
print('close avg/min/max:', r)
r2 = con.execute("SELECT SUM(volume), SUM(volume * close * 1000) / 1e9, SUM(volume * close) / 1e6 FROM core.market_ohlcv_daily WHERE date = '2026-10-09'").fetchone()
print('volume sum, val in bil (close*1000/1e9):', r2)

# Check foreign net flow
ff = con.execute("SELECT date, buy_value, sell_value, net_value FROM core.market_foreign_flow_daily ORDER BY date DESC LIMIT 5").fetchall()
print('Foreign flow top 5:', ff)

# Check market breadth
br = con.execute("SELECT date, advancing, declining, unchanged, ratio_advance_decline, pct_above_ma20 FROM core.market_breadth_series ORDER BY date DESC LIMIT 5").fetchall()
print('Breadth top 5:', br)

# Check sentiment
sent = con.execute("SELECT date, sentiment_score, fear_greed_score, sentiment_label FROM core.market_sentiment_snapshot ORDER BY date DESC LIMIT 5").fetchall()
print('Sentiment top 5:', sent)

# Check derivatives
deriv = con.execute("SELECT symbol, date, open, high, low, close, volume, open_interest FROM core.market_derivatives_daily ORDER BY date DESC LIMIT 5").fetchall()
print('Derivatives top 5:', deriv)

# Check ETF
etf = con.execute("SELECT symbol, date, close, volume, nav, premium_discount FROM core.market_etf_daily ORDER BY date DESC LIMIT 5").fetchall()
print('ETF top 5:', etf)

# Check CW
cw = con.execute("SELECT symbol, date, close, volume, exercise_price, days_to_expiry FROM core.market_covered_warrants_daily ORDER BY date DESC LIMIT 5").fetchall()
print('CW top 5:', cw)
