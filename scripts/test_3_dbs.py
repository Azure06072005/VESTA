import duckdb
import os

SNAPSHOT_DB_PATH = "db/vesta_snapshot.duckdb"
NEWS_DB_PATH = "db/vesta_news.duckdb"
OHLCV_DB_PATH = "db/vesta_ohlcv.duckdb"

print("1. Testing Snapshot DB:")
with duckdb.connect(SNAPSHOT_DB_PATH, read_only=True) as con:
    ev_cnt = con.execute("SELECT count(*) FROM core.corporate_events").fetchone()[0]
    sym_cnt = con.execute("SELECT count(*) FROM core.dim_symbol").fetchone()[0]
    print(f"   Corporate events: {ev_cnt}, Dim symbols: {sym_cnt}")
    events = con.execute("SELECT symbol, event_type, event_title, ex_date FROM core.corporate_events ORDER BY ex_date DESC LIMIT 3").fetchall()
    print(f"   Sample events: {events}")

print("\n2. Testing News DB:")
with duckdb.connect(NEWS_DB_PATH, read_only=True) as con:
    news_cnt = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
    print(f"   News count: {news_cnt}")
    news = con.execute("SELECT symbol, headline, source, published_at FROM core.news ORDER BY published_at DESC LIMIT 3").fetchall()
    print(f"   Sample news: {news}")

print("\n3. Testing OHLCV DB:")
with duckdb.connect(OHLCV_DB_PATH, read_only=True) as con:
    ohlcv_cnt = con.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
    ohlcv_1m_cnt = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    print(f"   OHLCV daily: {ohlcv_cnt}, OHLCV 1m: {ohlcv_1m_cnt}")
    vic_bars = con.execute("SELECT date, open, high, low, close, volume FROM core.market_ohlcv_daily WHERE symbol = 'VIC' ORDER BY date DESC LIMIT 3").fetchall()
    print(f"   Sample VIC bars: {vic_bars}")

print("\nALL THREE DATABASES VERIFIED SUCCESSFULLY!")
