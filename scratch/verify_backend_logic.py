import duckdb
import json
import re

# 1. Test Corporate Events
con_snap = duckdb.connect("d:/VESTA/db/vesta_snapshot.duckdb", read_only=True)
ev_rows = con_snap.execute("""
    SELECT symbol, event_type, event_date, detail_json 
    FROM core.corporate_events 
    ORDER BY event_date DESC 
    LIMIT 10
""").fetchall()
events = []
for r in ev_rows:
    title = r[1]
    ex_d = str(r[2])[:10] if r[2] else "-"
    rec_d = "-"
    imp_d = "-"
    if r[3]:
        try:
            d = json.loads(r[3])
            title = d.get("event_title") or d.get("event_name") or d.get("content") or d.get("event_desc") or r[1]
            ex_d = d.get("ex_date") or ex_d
            rec_d = d.get("record_date") or "-"
            imp_d = d.get("implementation_date") or d.get("payout_date") or "-"
        except Exception:
            pass
    events.append({
        "symbol": r[0],
        "event_type": r[1],
        "event_title": title,
        "ex_date": ex_d,
        "record_date": rec_d,
        "implementation_date": imp_d,
    })
print(f"Events extracted: {len(events)}, Sample: {events[0]['symbol']} | {events[0]['event_type']} | {events[0]['ex_date']}")
con_snap.close()

# 2. Test News Pagination & Search
con_news = duckdb.connect("d:/VESTA/db/vesta_news.duckdb", read_only=True)
p = 1
ps = 10
news_rows = con_news.execute("""
    SELECT symbol, headline, source, published_at, source_url, body, summary 
    FROM core.news 
    ORDER BY published_at DESC 
    LIMIT ? OFFSET ?
""", [ps, (p - 1) * ps]).fetchall()
print(f"News page {p}: {len(news_rows)} articles. Sample headline: {news_rows[0][1][:40]}")
con_news.close()

# 3. Test OHLCV 1m and daily
con_ohlcv = duckdb.connect("d:/VESTA/db/vesta_ohlcv.duckdb", read_only=True)
fpt_1m = con_ohlcv.execute("SELECT time, open, high, low, close, volume FROM core.market_ohlcv_1m WHERE symbol='FPT' ORDER BY time DESC LIMIT 5").fetchall()
print(f"FPT 1M rows: {len(fpt_1m)}")

fpt_daily = con_ohlcv.execute("SELECT date, open, high, low, close, volume FROM core.market_ohlcv_daily WHERE symbol='FPT' ORDER BY date DESC LIMIT 5").fetchall()
print(f"FPT Daily rows: {len(fpt_daily)}")

fpt_5m = con_ohlcv.execute("""
    SELECT time_bucket(INTERVAL '5 minutes', time) as bar_time,
           FIRST(open ORDER BY time ASC) as open,
           MAX(high) as high,
           MIN(low) as low,
           LAST(close ORDER BY time ASC) as close,
           SUM(volume) as volume
    FROM core.market_ohlcv_1m
    WHERE symbol='FPT'
    GROUP BY bar_time
    ORDER BY bar_time DESC
    LIMIT 5
""").fetchall()
print(f"FPT 5M aggregated rows: {len(fpt_5m)}")
con_ohlcv.close()
