"""scratch/exact_audit_all_60_keys.py

Audits exact non-null count and non-zero count for ALL 60 keys across all 46,337 rows in core.fundamentals (report_type = 'ratio')
"""
import sys
import json
import duckdb
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

print("Fetching all 46,337 ratio rows from core.fundamentals...")
df = con.execute("""
    SELECT data_json 
    FROM core.fundamentals 
    WHERE report_type = 'ratio' AND data_json IS NOT NULL
""").df()
con.close()

total_rows = len(df)
print(f"Total rows fetched: {total_rows:,}. Calculating exact fill rates...")

# Collect all keys
all_keys_stats = {}
for j_str in df["data_json"]:
    try:
        clean_j = j_str.replace("NaN", "null").replace("Infinity", "null")
        d = json.loads(clean_j)
        for k, v in d.items():
            if k not in all_keys_stats:
                all_keys_stats[k] = {"non_null": 0, "non_zero": 0, "total": 0}
            all_keys_stats[k]["total"] += 1
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                all_keys_stats[k]["non_null"] += 1
                if v != 0:
                    all_keys_stats[k]["non_zero"] += 1
    except Exception:
        pass

rows = []
for k, stats in all_keys_stats.items():
    total = stats["total"]
    nn = stats["non_null"]
    nz = stats["non_zero"]
    fill_rate = (nn / total) * 100.0
    active_rate = (nz / total) * 100.0
    rows.append({
        "key": k,
        "non_null_count": nn,
        "fill_rate_pct": round(fill_rate, 2),
        "non_zero_count": nz,
        "active_rate_pct": round(active_rate, 2),
        "total": total,
        "status": "EXCLUDE (100% NaN)" if nn == 0 else "RETAIN (Has Data)"
    })

df_res = pd.DataFrame(rows).sort_values(by=["fill_rate_pct", "key"], ascending=[False, True])

print("\n" + "=" * 95)
print(f"EXACT 100% AUDIT OF ALL RATIO KEYS ACROSS {total_rows:,} ROWS")
print("=" * 95)
print(df_res.to_string(index=False))

# Group by status
retained = df_res[df_res["status"] == "RETAIN (Has Data)"]
excluded = df_res[df_res["status"] == "EXCLUDE (100% NaN)"]

print("\n" + "=" * 95)
print(f"SUMMARY: {len(retained)} KEYS TO RETAIN vs {len(excluded)} KEYS TO EXCLUDE (100% NaN)")
print("=" * 95)
print(f"Retained Keys Count: {len(retained)}")
print(f"Excluded Keys Count: {len(excluded)}")
print("Excluded keys list:", list(excluded["key"].values))
