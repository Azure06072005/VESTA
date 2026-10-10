import duckdb

con = duckdb.connect("db/vesta_ohlcv.duckdb", read_only=True)
res = con.execute("SELECT table_name, table_type FROM information_schema.tables WHERE table_schema='core' AND table_name IN ('cafef_disclosures', 'company_overview', 'corporate_events')").fetchall()
print("Tables in ohlcv:", res)
con.close()
