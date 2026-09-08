import duckdb
con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)
count = con.execute("SELECT count(*) FROM core.news WHERE source='cafef'").fetchone()[0]
symbols = con.execute("SELECT count(DISTINCT symbol) FROM core.news WHERE source='cafef'").fetchone()[0]
print(f'Total Cafef (F004) rows successfully saved in database: {count}')
print(f'Total unique symbols covered by Cafef so far: {symbols}')
