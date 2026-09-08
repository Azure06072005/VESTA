import duckdb

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
print("Schema:")
print(conn.execute("PRAGMA table_info('core.market_index_daily')").df()[['name', 'type', 'notnull', 'pk']])
print("\nSample:")
print(conn.execute("SELECT * FROM core.market_index_daily LIMIT 5").df())
print("\nIndices currently tracked:")
print(conn.execute("SELECT index_code, MIN(trading_date), MAX(trading_date), COUNT(*) FROM core.market_index_daily GROUP BY index_code").df())
conn.close()
