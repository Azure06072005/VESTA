import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)
row = con.execute("SELECT symbol, published_at, headline, source_url FROM core.news WHERE source='cafef' ORDER BY published_at DESC LIMIT 1").fetchone()
print(f"[{row[0]}] {row[1]} - {row[2]}")
print(f"URL: {row[3]}")
