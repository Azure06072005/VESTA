import duckdb

con = duckdb.connect("db/vesta.duckdb", read_only=False)
con.execute("ATTACH 'db/vesta_latest_backup.duckdb' AS backup_db (READ_ONLY);")
con.execute("""
    INSERT INTO core.macro_policy
    SELECT * FROM backup_db.core.macro_policy
    ON CONFLICT (source_url) DO NOTHING
""")
con.execute("DETACH backup_db;")
final_cnt = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
print(f"vesta.duckdb core.macro_policy FINAL COUNT: {final_cnt:,}")
con.close()
