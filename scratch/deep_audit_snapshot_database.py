import json
import os
import sys
import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

db_path = "db/vesta_backup.duckdb"
if not os.path.exists(db_path):
    db_path = "db/vesta_snapshot.duckdb"

print(f"=== DEEP AUDIT OF SNAPSHOT DATABASE: {db_path} ===")
con = duckdb.connect(db_path, read_only=True)

# List all tables and views in all schemas
tables = con.execute("""
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
    ORDER BY table_schema, table_name
""").df()

print(f"\nTotal tables & views: {len(tables)}")
print(tables.to_string())

audit_report = {}

for idx, row in tables.iterrows():
    schema = row['table_schema']
    tbl = row['table_name']
    t_type = row['table_type']
    full_name = f"{schema}.{tbl}"
    
    try:
        cnt = con.execute(f"SELECT count(*) FROM {full_name}").fetchone()[0]
        cols_df = con.execute(f"DESCRIBE {full_name}").df()
        
        col_details = []
        for _, c_row in cols_df.iterrows():
            c_name = c_row['column_name']
            c_type = c_row['column_type']
            col_details.append({'name': c_name, 'type': c_type})
            
        audit_report[full_name] = {
            'schema': schema,
            'table': tbl,
            'type': t_type,
            'row_count': cnt,
            'col_count': len(cols_df),
            'columns': col_details
        }
    except Exception as e:
        print(f"Error reading {full_name}: {e}")

con.close()

# Save structured summary to scratch
out_json = "scratch/snapshot_database_deep_audit.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(audit_report, f, indent=2, ensure_ascii=False)

print(f"\n✅ Đã lưu kết quả kiểm toán chi tiết vào: {out_json}")

# In tóm tắt các bảng trọng điểm của Fundamentals & Governance
print("\n=== TỔNG KẾT CÁC BẢNG TRỌNG ĐIỂM TRONG SNAPSHOT DATABASE ===")
for tbl, info in audit_report.items():
    if info['schema'] == 'core' and info['type'] == 'BASE TABLE':
        print(f"📊 {tbl:35s}: {info['row_count']:>10,} dòng | {info['col_count']:2d} cột")
