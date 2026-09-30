import duckdb

c_snap = duckdb.connect("d:/VESTA/db/vesta_snapshot.duckdb", read_only=True)
c_main = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)

snap_tables = {f"{s}.{t}": c_snap.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
               for s, t in c_snap.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'meta', 'preprocessed', 'staging')").fetchall()}

main_tables = {f"{s}.{t}": c_main.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
               for s, t in c_main.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'meta', 'preprocessed', 'staging')").fetchall()}

print(f"{'Table':<35} | {'vesta_snapshot.duckdb':<22} | {'vesta.duckdb':<15}")
print("-" * 80)
all_keys = sorted(set(snap_tables.keys()) | set(main_tables.keys()))
for k in all_keys:
    s_cnt = f"{snap_tables.get(k, 0):,}" if k in snap_tables else "MISSING"
    m_cnt = f"{main_tables.get(k, 0):,}" if k in main_tables else "MISSING"
    if s_cnt != m_cnt:
        print(f"{k:<35} | {s_cnt:<22} | {m_cnt:<15}")

c_snap.close()
c_main.close()
