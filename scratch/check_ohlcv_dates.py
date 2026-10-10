import duckdb

con = duckdb.connect('db/vesta_ohlcv.duckdb', read_only=True)
tables = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core'").fetchall()
for t in tables:
    tname = t[0]
    cols = [c[1] for c in con.execute(f'PRAGMA table_info(core.{tname})').fetchall()]
    dcol = next((c for c in cols if c in ['date', 'time', 'trade_date']), None)
    if dcol:
        res = con.execute(f'SELECT MIN("{dcol}")::VARCHAR, MAX("{dcol}")::VARCHAR, COUNT(*) FROM core.{tname}').fetchone()
        print(f"{tname:32}: {res[2]:10,d} rows | {dcol:6} | {res[0]} -> {res[1]}")
    else:
        print(f"{tname:32}: {con.execute(f'SELECT COUNT(*) FROM core.{tname}').fetchone()[0]:10,d} rows | cols: {cols[:4]}")
con.close()
