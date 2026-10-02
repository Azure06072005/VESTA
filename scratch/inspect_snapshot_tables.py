import duckdb

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
for t in ['market_ohlcv_daily', 'news', 'pit_events', 'fundamentals', 'price_adjustment_events', 'corporate_events']:
    row = con.execute("SELECT table_type FROM information_schema.tables WHERE table_schema='core' AND table_name=?", [t]).fetchone()
    cnt = con.execute(f"SELECT count(*) FROM core.{t}").fetchone()[0]
    ttype = row[0] if row else "MISSING"
    print(f"{t:25}: type={ttype}, rows={cnt:,}")
con.close()
