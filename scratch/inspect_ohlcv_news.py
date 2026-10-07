import duckdb
import os

def inspect_single(name, path):
    print(f"\n==========================================")
    print(f"DATABASE: {name} ({path})")
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"File Size: {size_mb:.2f} MB ({size_mb/1024:.2f} GB)")
    print(f"==========================================")
    con = duckdb.connect(path, read_only=True)
    tables = con.execute("""
        SELECT table_schema, table_name, table_type 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name
    """).fetchall()
    
    print(f"Found {len(tables)} tables/views:")
    for schema, table, t_type in tables:
        full_name = f"{schema}.{table}"
        try:
            cnt = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
            cols = con.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = '{schema}' AND table_name = '{table}'
                ORDER BY ordinal_position
            """).fetchall()
            col_names = [c[0] for c in cols]
            extra = []
            date_cols = [c for c in col_names if 'time' in c or 'date' in c or 'publish' in c]
            if date_cols and cnt > 0:
                d_col = date_cols[0]
                try:
                    min_d, max_d = con.execute(f"SELECT MIN({d_col}), MAX({d_col}) FROM {full_name}").fetchone()
                    extra.append(f"range({d_col}): [{min_d} to {max_d}]")
                except Exception:
                    pass
            sym_cols = [c for c in col_names if c in ('symbol', 'ticker', 'code')]
            if sym_cols and cnt > 0:
                s_col = sym_cols[0]
                try:
                    n_sym = con.execute(f"SELECT COUNT(DISTINCT {s_col}) FROM {full_name}").fetchone()[0]
                    extra.append(f"unique({s_col}): {n_sym}")
                except Exception:
                    pass
            extra_str = (" | " + ", ".join(extra)) if extra else ""
            print(f"  - [{t_type}] {full_name}: {cnt:,} rows, {len(cols)} cols{extra_str}")
            print(f"      Columns: {', '.join(col_names[:12])}{' ...' if len(col_names) > 12 else ''}")
        except Exception as e:
            print(f"  - [{t_type}] {full_name}: Error: {e}")
    con.close()

if __name__ == "__main__":
    inspect_single("vesta_ohlcv", "d:/VESTA/db/vesta_ohlcv.duckdb")
    inspect_single("vesta_news", "d:/VESTA/db/vesta_news.duckdb")
