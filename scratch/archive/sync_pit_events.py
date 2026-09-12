import duckdb

con = duckdb.connect("db/vesta_latest_backup.duckdb", read_only=False)
con.execute("ATTACH 'db/vesta.duckdb' AS main_db (READ_ONLY);")
con.execute("TRUNCATE core.pit_events;")
con.execute("INSERT INTO core.pit_events SELECT * FROM main_db.core.pit_events;")
con.execute("DETACH main_db;")
cnt = con.execute("SELECT count(*) FROM core.pit_events").fetchone()[0]
print(f"vesta_latest_backup.duckdb core.pit_events final count: {cnt:,}")
con.close()
