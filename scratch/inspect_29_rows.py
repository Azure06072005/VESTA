import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)
df = con.execute("""
    SELECT source, symbol, headline, published_at, available_at, 
           EXTRACT(EPOCH FROM (published_at - available_at)) as diff_sec
    FROM core.news
    WHERE available_at < published_at
""").fetchdf()

print(f"Total rows where available_at < published_at: {len(df)}")
for idx, r in df.iterrows():
    print(f"[{r['source']}] {r['symbol']}: pub={r['published_at']}, avail={r['available_at']}, diff={r['diff_sec']}s | {r['headline'][:60]}")

con.close()
