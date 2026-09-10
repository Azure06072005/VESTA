import duckdb
con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)
count = con.execute("SELECT count(*) FROM core.news WHERE symbol='FPT' AND source='cafef'").fetchone()[0]
print(f'Total FPT rows in core.news: {count}')
