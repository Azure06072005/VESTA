import duckdb
import time

print("Starting Smart Sync into vesta_latest_backup.duckdb...")
start_time = time.time()

con = duckdb.connect("d:/VESTA/db/vesta_latest_backup.duckdb", read_only=False)

def _table_has_column(conn, table_schema, table_name, column_name):
    res = conn.execute(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = ? AND table_name = ? AND column_name = ?",
        [table_schema, table_name, column_name]
    ).fetchone()
    return (res[0] if res else 0) > 0

# Step 0: Ensure schema migrations are applied on backup
print("Checking and applying source column migration on backup...")
for schema in [("staging", "fundamentals"), ("core", "fundamentals")]:
    ts, tn = schema
    if not _table_has_column(con, ts, tn, "source"):
        print(f"Adding source column to {ts}.{tn}...")
        con.execute(f"ALTER TABLE {ts}.{tn} ADD COLUMN source VARCHAR DEFAULT 'vnstock_data'")
        con.execute(f"""
            UPDATE {ts}.{tn}
            SET source = 'cafef'
            WHERE NOT (
                fetched_at < '2026-09-06'
                OR data_json LIKE '%"BS_%'
                OR data_json LIKE '%"IS_%'
                OR data_json LIKE '%"CF_%'
                OR data_json LIKE '%"RT_%'
            )
        """)
        print(f"[migration] {ts}.{tn}: source column added & backfilled.")

con.execute("ATTACH 'd:/VESTA/db/vesta.duckdb' AS live (READ_ONLY)")

# 1. core.fundamentals & staging.fundamentals
print("Syncing 24 new fundamentals rows...")
con.execute("""
    INSERT INTO core.fundamentals 
    SELECT * FROM live.core.fundamentals 
    WHERE (symbol, report_type, period_end, fetched_at) NOT IN (
        SELECT symbol, report_type, period_end, fetched_at FROM core.fundamentals
    )
""")
con.execute("""
    INSERT INTO staging.fundamentals 
    SELECT * FROM live.staging.fundamentals 
    WHERE (symbol, report_type, period_end, fetched_at) NOT IN (
        SELECT symbol, report_type, period_end, fetched_at FROM staging.fundamentals
    )
""")

# 2. core.macro_policy & staging.macro_policy
print("Syncing 1,661 macro_policy rows...")
con.execute("""
    INSERT INTO core.macro_policy 
    SELECT * FROM live.core.macro_policy 
    WHERE source_url NOT IN (SELECT source_url FROM core.macro_policy)
""")
con.execute("""
    INSERT INTO staging.macro_policy 
    SELECT * FROM live.staging.macro_policy 
    WHERE source_url NOT IN (SELECT source_url FROM staging.macro_policy)
""")

# 3. core.market_index_daily
print("Syncing 4 market_index_daily rows...")
con.execute("""
    INSERT INTO core.market_index_daily 
    SELECT * FROM live.core.market_index_daily 
    WHERE (index_code, date) NOT IN (
        SELECT index_code, date FROM core.market_index_daily
    )
""")

# 4. core.pit_events & staging.pit_events
print("Syncing 1,228 pit_events...")
con.execute("DELETE FROM core.pit_events")
con.execute("INSERT INTO core.pit_events SELECT * FROM live.core.pit_events")
con.execute("DELETE FROM staging.pit_events")
con.execute("INSERT INTO staging.pit_events SELECT * FROM live.staging.pit_events")

# 5. core.realtime_quote_snapshot & staging.realtime_quote_snapshot
print("Syncing 5 realtime_quote_snapshot rows...")
con.execute("""
    INSERT INTO core.realtime_quote_snapshot 
    SELECT * FROM live.core.realtime_quote_snapshot 
    WHERE (symbol, snapshot_at) NOT IN (
        SELECT symbol, snapshot_at FROM core.realtime_quote_snapshot
    )
""")
con.execute("""
    INSERT INTO staging.realtime_quote_snapshot 
    SELECT * FROM live.staging.realtime_quote_snapshot 
    WHERE (symbol, snapshot_at) NOT IN (
        SELECT symbol, snapshot_at FROM staging.realtime_quote_snapshot
    )
""")

# Check counts in vesta_latest_backup
print("--- Final Verified Counts in vesta_latest_backup.duckdb ---")
for tbl in [
    'core.dim_symbol', 
    'core.fundamentals', 
    'core.macro_policy', 
    'core.market_index_daily', 
    'core.pit_events',
    'core.realtime_quote_snapshot',
    'staging.fundamentals',
    'staging.macro_policy',
    'staging.pit_events'
]:
    cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
    print(f"  {tbl:<35}: {cnt:,}")

con.close()
elapsed = time.time() - start_time
print(f"Smart Sync completed successfully in {elapsed:.2f} seconds.")
