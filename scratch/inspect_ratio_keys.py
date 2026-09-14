"""scratch/inspect_ratio_keys.py

Inspects JSON keys in core.fundamentals across report_types: ratio, income_statement, balance_sheet, cash_flow
"""
import sys
import json
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

sample = con.execute("SELECT data_json FROM core.fundamentals WHERE report_type = 'ratio' LIMIT 1").fetchone()[0]
clean_j = sample.replace("NaN", "null").replace("Infinity", "null")
data = json.loads(clean_j)
print("=== ALL 60 KEYS IN REPORT_TYPE = RATIO ===")
for idx, (k, v) in enumerate(data.items()):
    print(f"{idx+1:>2}. {k:<35} : {v}")

con.close()
