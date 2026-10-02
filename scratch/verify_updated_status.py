import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("=== [1] KIỂM TRA VESTA_SNAPSHOT.DUCKDB ===")
conn_snap = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
tables_snap = [
    'order_book_depth', 'intraday_trades', 'market_screener_snapshot',
    'realtime_quote_snapshot', 'market_sentiment_snapshot', 'market_breadth_series',
    'cafef_disclosures', 'corporate_events'
]
for t in tables_snap:
    cols = [c[0] for c in conn_snap.execute(f"DESCRIBE core.{t}").fetchall()]
    tc = next((c for c in cols if any(k in c.lower() for k in ['time', 'date', 'published', 'snapshot'])), None)
    cnt = conn_snap.execute(f"SELECT count(*) FROM core.{t}").fetchone()[0]
    max_v = conn_snap.execute(f"SELECT max({tc}) FROM core.{t}").fetchone()[0] if tc else "N/A"
    print(f"  • core.{t:28}: count = {cnt:>8,}, col = {tc}, max = {max_v}")
conn_snap.close()

print("\n=== [2] KIỂM TRA VESTA_OHLCV.DUCKDB ===")
conn_ohlcv = duckdb.connect('d:/VESTA/db/vesta_ohlcv.duckdb', read_only=True)
r_ohlcv = conn_ohlcv.execute("SELECT count(*), max(date) FROM core.market_ohlcv_daily").fetchone()
print(f"  • core.market_ohlcv_daily          : count = {r_ohlcv[0]:>8,}, max_date = {r_ohlcv[1]}")

indices = conn_ohlcv.execute("SELECT index_code, count(*), max(date) FROM core.market_index_daily WHERE index_code IN ('VNINDEX', 'VN30', 'HNX-INDEX', 'HNX30', 'UPCOM-INDEX', 'VN100') GROUP BY index_code ORDER BY index_code").fetchall()
for idx, cnt, md in indices:
    print(f"  • core.market_index_daily ({idx:11}): count = {cnt:>8,}, max_date = {md}")
conn_ohlcv.close()

print("\n=== [3] KIỂM TRA VESTA_NEWS.DUCKDB ===")
conn_news = duckdb.connect('d:/VESTA/db/vesta_news.duckdb', read_only=True)
total_news, max_pub = conn_news.execute("SELECT count(*), max(published_at) FROM core.news").fetchone()
today_news = conn_news.execute("SELECT count(*) FROM core.news WHERE CAST(published_at AS DATE) >= '2026-10-01'").fetchone()[0]
print(f"  • core.news (Toàn bộ bài viết)     : count = {total_news:>8,}, max_published = {max_pub}, tin_T0_T1 = {today_news:>5,}")

by_type = conn_news.execute("SELECT news_type, count(*), max(published_at) FROM core.news GROUP BY news_type ORDER BY count(*) DESC").fetchall()
for ntype, cnt, mp in by_type:
    print(f"    - {ntype:22}: count = {cnt:>8,}, max_published = {mp}")

res_cnt, res_max = conn_news.execute("SELECT count(*), max(published_at) FROM core.news_resources").fetchone()
print(f"  • core.news_resources (Tin vĩ mô)  : count = {res_cnt:>8,}, max_published = {res_max}")

macro_cnt, macro_max = conn_news.execute("SELECT count(*), max(published_at) FROM core.macro_policy").fetchone()
print(f"  • core.macro_policy (Chính sách)   : count = {macro_cnt:>8,}, max_published = {macro_max}")

conn_news.close()

