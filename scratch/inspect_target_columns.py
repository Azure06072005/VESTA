import sys
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_backup.duckdb", read_only=True)
for t in ['fundamentals', 'corporate_events', 'financial_notes', 'market_foreign_flow_daily', 'proprietary_flow']:
    print(f"\n=== COLUMNS FOR core.{t} ===")
    cols = con.execute(f"DESCRIBE core.{t}").df()
    print(cols[['column_name', 'column_type']].to_string(index=False))
con.close()
