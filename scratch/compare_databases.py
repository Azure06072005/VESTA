import duckdb
import os
import pathlib
import json

db_canonical = "db/vesta.duckdb"
db_snapshot = "db/vesta_snapshot.duckdb"

con_c = duckdb.connect(db_canonical, read_only=True)
con_s = duckdb.connect(db_snapshot, read_only=True)

size_c = os.path.getsize(db_canonical)
size_s = os.path.getsize(db_snapshot)

# Get all tables from both databases (excluding system schemas)
query_tables = """
SELECT schema_name, table_name 
FROM duckdb_tables() 
WHERE schema_name NOT IN ('information_schema', 'pg_catalog') 
ORDER BY schema_name, table_name
"""
tables_c = con_c.execute(query_tables).fetchall()
tables_s = con_s.execute(query_tables).fetchall()

set_c = {(s, t) for s, t in tables_c}
set_s = {(s, t) for s, t in tables_s}

common = sorted(list(set_c & set_s))
only_c = sorted(list(set_c - set_s))
only_s = sorted(list(set_s - set_c))

print(f"=== DATABASE OVERVIEW ===")
print(f"vesta.duckdb (canonical):          {size_c / (1024**3):.2f} GB ({size_c:,} bytes)")
print(f"vesta_snapshot.duckdb (snapshot):  {size_s / (1024**3):.2f} GB ({size_s:,} bytes)")
print(f"Tables in vesta.duckdb:          {len(set_c)}")
print(f"Tables in vesta_snapshot.duckdb: {len(set_s)}")
print(f"Common tables:                   {len(common)}")
print(f"Only in vesta.duckdb:            {len(only_c)}")
print(f"Only in vesta_snapshot.duckdb:   {len(only_s)}")

results = []
total_rows_c = 0
total_rows_s = 0

for s, t in common:
    full_tbl = f'"{s}"."{t}"'
    tbl_key = f"{s}.{t}"
    
    # Row count
    try:
        cnt_c = con_c.execute(f"SELECT count(*) FROM {full_tbl}").fetchone()[0]
    except Exception as e:
        cnt_c = -1
    try:
        cnt_s = con_s.execute(f"SELECT count(*) FROM {full_tbl}").fetchone()[0]
    except Exception as e:
        cnt_s = -1

    if cnt_c > 0:
        total_rows_c += cnt_c
    if cnt_s > 0:
        total_rows_s += cnt_s

    # Columns and types
    cols_c_info = con_c.execute(f"PRAGMA table_info('{s}.{t}')").fetchall()
    cols_s_info = con_s.execute(f"PRAGMA table_info('{s}.{t}')").fetchall()
    
    cols_c_dict = {r[1]: r[2] for r in cols_c_info}
    cols_s_dict = {r[1]: r[2] for r in cols_s_info}
    
    cols_c = list(cols_c_dict.keys())
    cols_s = list(cols_s_dict.keys())
    
    col_only_in_c = [c for c in cols_c if c not in cols_s_dict]
    col_only_in_s = [c for c in cols_s if c not in cols_c_dict]
    type_diff = {c: {"vesta": cols_c_dict[c], "snapshot": cols_s_dict[c]} for c in cols_c if c in cols_s_dict and cols_c_dict[c] != cols_s_dict[c]}

    # Detect Date & Symbol columns
    date_col = None
    sym_col = None
    for candidate in ("date", "time", "published_at", "event_date", "period_end", "period_date", "trade_date"):
        if candidate in cols_s:
            date_col = candidate
            break
    for candidate in ("symbol", "code", "ticker"):
        if candidate in cols_s:
            sym_col = candidate
            break

    details = {
        "table": tbl_key,
        "schema": s,
        "name": t,
        "rows_vesta": cnt_c,
        "rows_snapshot": cnt_s,
        "delta": cnt_s - cnt_c if cnt_c >= 0 and cnt_s >= 0 else None,
        "col_only_in_vesta": col_only_in_c,
        "col_only_in_snapshot": col_only_in_s,
        "type_diff": type_diff,
        "col_count_vesta": len(cols_c),
        "col_count_snapshot": len(cols_s)
    }

    if date_col:
        try:
            r_c = con_c.execute(f"SELECT CAST(MIN({date_col}) AS VARCHAR), CAST(MAX({date_col}) AS VARCHAR) FROM {full_tbl}").fetchone()
            details["c_min_date"] = str(r_c[0])[:19] if r_c and r_c[0] else None
            details["c_max_date"] = str(r_c[1])[:19] if r_c and r_c[1] else None
        except Exception:
            pass
        try:
            r_s = con_s.execute(f"SELECT CAST(MIN({date_col}) AS VARCHAR), CAST(MAX({date_col}) AS VARCHAR) FROM {full_tbl}").fetchone()
            details["s_min_date"] = str(r_s[0])[:19] if r_s and r_s[0] else None
            details["s_max_date"] = str(r_s[1])[:19] if r_s and r_s[1] else None
        except Exception:
            pass
        details["date_col"] = date_col

    if sym_col:
        try:
            syms_c = con_c.execute(f"SELECT COUNT(DISTINCT {sym_col}) FROM {full_tbl}").fetchone()[0]
            details["c_syms"] = syms_c
        except Exception:
            pass
        try:
            syms_s = con_s.execute(f"SELECT COUNT(DISTINCT {sym_col}) FROM {full_tbl}").fetchone()[0]
            details["s_syms"] = syms_s
        except Exception:
            pass
        details["sym_col"] = sym_col

    results.append(details)

# Tables only in vesta
only_c_details = []
for s, t in only_c:
    full_tbl = f'"{s}"."{t}"'
    try:
        cnt = con_c.execute(f"SELECT count(*) FROM {full_tbl}").fetchone()[0]
        if cnt > 0:
            total_rows_c += cnt
    except Exception:
        cnt = -1
    cols = [r[1] for r in con_c.execute(f"PRAGMA table_info('{s}.{t}')").fetchall()]
    only_c_details.append({"table": f"{s}.{t}", "rows": cnt, "cols": len(cols)})

# Tables only in snapshot
only_s_details = []
for s, t in only_s:
    full_tbl = f'"{s}"."{t}"'
    try:
        cnt = con_s.execute(f"SELECT count(*) FROM {full_tbl}").fetchone()[0]
        if cnt > 0:
            total_rows_s += cnt
    except Exception:
        cnt = -1
    cols = [r[1] for r in con_s.execute(f"PRAGMA table_info('{s}.{t}')").fetchall()]
    only_s_details.append({"table": f"{s}.{t}", "rows": cnt, "cols": len(cols)})

con_c.close()
con_s.close()

output_data = {
    "size_canonical": size_c,
    "size_snapshot": size_s,
    "total_rows_canonical": total_rows_c,
    "total_rows_snapshot": total_rows_s,
    "tables_canonical_count": len(set_c),
    "tables_snapshot_count": len(set_s),
    "common_count": len(common),
    "common": results,
    "only_in_canonical": only_c_details,
    "only_in_snapshot": only_s_details,
}

out_path = pathlib.Path("scratch/db_comparison_results.json")
out_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
print("\n" + "="*50)
print(f"Results successfully saved to {out_path}")
print(f"Total Rows vesta.duckdb:          {total_rows_c:,}")
print(f"Total Rows vesta_snapshot.duckdb: {total_rows_s:,}")
print(f"Total Row Delta (Snapshot - Canonical): {total_rows_s - total_rows_c:+,}")
print("="*50)
