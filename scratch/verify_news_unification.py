import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)
print("=== COLUMNS IN core.news (UNIFIED) ===")
cols = con.execute("""
    SELECT column_name, data_type, is_nullable 
    FROM information_schema.columns 
    WHERE table_schema='core' AND table_name='news'
    ORDER BY ordinal_position
""").fetchall()
for col, dtype, nullable in cols:
    print(f"  {col:<16} {dtype:<12} (Nullable: {nullable})")

print("\n=== SAMPLE COUNTS ===")
total_news = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
stock_news = con.execute("SELECT count(*) FROM core.v_stock_news").fetchone()[0]
macro_news = con.execute("SELECT count(*) FROM core.v_macro_news").fetchone()[0]
fpt_news = con.execute("SELECT count(*) FROM core.news WHERE symbol = 'FPT'").fetchone()[0]
vnm_news = con.execute("SELECT count(*) FROM core.news WHERE symbol = 'VNM'").fetchone()[0]
res_cnt = con.execute("SELECT count(*) FROM core.news_resources").fetchone()[0]
macro_cnt = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]

print(f"Total unified news: {total_news:,}")
print(f"Stock news (v_stock_news): {stock_news:,}")
print(f"Macro news (v_macro_news): {macro_news:,}")
print(f"FPT news: {fpt_news:,}")
print(f"VNM news: {vnm_news:,}")
print(f"Backward compatibility core.news_resources: {res_cnt:,}")
print(f"Backward compatibility core.macro_policy: {macro_cnt:,}")

print("\n=== NEWS TYPE BREAKDOWN ===")
types = con.execute("SELECT news_type, count(*) FROM core.news GROUP BY news_type ORDER BY count(*) DESC").fetchall()
for t, c in types:
    print(f"  {t:<22} {c:,}")

print("\n=== SAMPLE ROW FROM EQUITY NEWS ===")
sample_eq = con.execute("SELECT source_url, news_type, symbol, source, headline, published_at FROM core.news WHERE symbol IS NOT NULL LIMIT 1").fetchdf()
print(sample_eq.to_dict(orient='records')[0])

print("\n=== SAMPLE ROW FROM MACRO NEWS ===")
sample_mc = con.execute("SELECT source_url, news_type, symbol, source, issuing_body, headline, published_at FROM core.news WHERE symbol IS NULL LIMIT 1").fetchdf()
print(sample_mc.to_dict(orient='records')[0])

con.close()
