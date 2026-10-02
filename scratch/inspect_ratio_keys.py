import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb
import json

con = duckdb.connect('db/vesta_backup.duckdb', read_only=True)
row = con.execute("SELECT symbol, period_end, data_json FROM core.fundamentals WHERE report_type = 'ratio' LIMIT 1").fetchone()
print(f"Symbol: {row[0]}, Period: {row[1]}")
d = json.loads(row[2])
print("Ratio keys count:", len(d))
print("Ratio sample keys:", list(d.keys())[:20])
for k in list(d.keys())[:10]:
    print(f"  {k}: {d[k]}")
con.close()
