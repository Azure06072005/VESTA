import duckdb
import os

path = "d:/VESTA/db/vesta_snapshot.duckdb"
con = duckdb.connect(path, read_only=True)
tables = con.execute("""
    SELECT table_schema, table_name, table_type 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name
""").fetchall()

print(f"DATABASE: vesta_snapshot ({os.path.getsize(path)/(1024*1024):.2f} MB)")
non_zero = []
for s, t, ty in tables:
    full = f"{s}.{t}"
    cnt = con.execute(f"SELECT count(*) FROM {full}").fetchone()[0]
    if cnt > 0:
        cols = con.execute(f"SELECT column_name FROM information_schema.columns WHERE table_schema='{s}' AND table_name='{t}' ORDER BY ordinal_position").fetchall()
        col_names = [c[0] for c in cols]
        date_cols = [c for c in col_names if 'time' in c or 'date' in c or 'publish' in c or 'created' in c or 'snapshot' in c or 'period' in c]
        d_info = ""
        if date_cols:
            dc = date_cols[0]
            try:
                m1, m2 = con.execute(f"SELECT min({dc}), max({dc}) FROM {full}").fetchone()
                d_info = f" | range({dc}): [{m1} to {m2}]"
            except:
                pass
        sym_cols = [c for c in col_names if c in ('symbol', 'ticker', 'code')]
        s_info = ""
        if sym_cols:
            sc = sym_cols[0]
            try:
                ns = con.execute(f"SELECT count(distinct {sc}) FROM {full}").fetchone()[0]
                s_info = f" | unique({sc}): {ns}"
            except:
                pass
        non_zero.append((full, ty, cnt, len(cols), d_info, s_info, col_names[:8]))

for full, ty, cnt, n_cols, d_info, s_info, sample_cols in non_zero:
    print(f"- [{ty}] {full}: {cnt:,} rows, {n_cols} cols{d_info}{s_info}")
    print(f"    Sample cols: {', '.join(sample_cols)}")
con.close()
