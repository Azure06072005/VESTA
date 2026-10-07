import duckdb
import glob

print("Checking OHLCV coverage across DBs:")
for p in glob.glob("db/*.duckdb"):
    try:
        con = duckdb.connect(p, read_only=True)
        tables = [t[0] for t in con.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE '%ohlcv%'").fetchall()]
        if tables:
            print(f"\nDB: {p} has tables: {tables}")
            for t in tables:
                schema = con.execute(f"SELECT table_schema FROM information_schema.tables WHERE table_name = '{t}'").fetchone()[0]
                cnt = con.execute(f'SELECT count(*) FROM "{schema}"."{t}"').fetchone()[0]
                symbols = [s[0] for s in con.execute(f'SELECT DISTINCT symbol FROM "{schema}"."{t}" LIMIT 5').fetchall()]
                date_range = con.execute(f'SELECT min(date), max(date) FROM "{schema}"."{t}"').fetchone()
                print(f"  {schema}.{t}: {cnt} rows | range: {date_range} | syms sample: {symbols}")
        con.close()
    except Exception as e:
        print(f"Error {p}: {e}")
