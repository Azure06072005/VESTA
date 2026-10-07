import duckdb
import os

path = "d:/VESTA/db/vesta_ohlcv.duckdb"
con = duckdb.connect(path, read_only=True)
tables = con.execute("""
    SELECT table_schema, table_name, table_type 
    FROM information_schema.tables 
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name
""").fetchall()

print(f"DATABASE: vesta_ohlcv ({os.path.getsize(path)/(1024*1024):.2f} MB)")
for s, t, ty in tables:
    full = f"{s}.{t}"
    cnt = con.execute(f"SELECT count(*) FROM {full}").fetchone()[0]
    cols = con.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='{s}' AND table_name='{t}' ORDER BY ordinal_position").fetchall()
    col_names = [c[0] for c in cols]
    
    date_info = ""
    date_cols = [c for c in col_names if 'time' in c or 'date' in c]
    if date_cols and cnt > 0:
        d = date_cols[0]
        try:
            m1, m2 = con.execute(f"SELECT min({d}), max({d}) FROM {full}").fetchone()
            date_info = f" | range({d}): [{m1} to {m2}]"
        except:
            pass
            
    sym_info = ""
    sym_cols = [c for c in col_names if c in ('symbol', 'ticker')]
    if sym_cols and cnt > 0:
        s_c = sym_cols[0]
        try:
            ns = con.execute(f"SELECT count(distinct {s_c}) FROM {full}").fetchone()[0]
            sym_info = f" | unique({s_c}): {ns}"
        except:
            pass
            
    print(f"- [{ty}] {full}: {cnt:,} rows, {len(cols)} cols{date_info}{sym_info}")
    if cnt > 0:
        print(f"    Cols: {', '.join(col_names[:12])}")
con.close()
