"""scratch/audit_ratio_keys_sparsity.py

Audits fill rate and data distribution for all 60 keys in core.fundamentals (report_type = 'ratio')
"""
import sys
import json
import duckdb
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

print("Auditing fill rate of 60 keys in core.fundamentals (report_type = 'ratio')...")
df = con.execute("""
    SELECT data_json 
    FROM core.fundamentals 
    WHERE report_type = 'ratio' AND data_json IS NOT NULL
""").df()

con.close()

# Sample 5,000 records across diverse periods and symbols to calculate fill rate accurately
sample_size = min(5000, len(df))
df_sample = df.sample(sample_size, random_state=42)

all_keys_stats = {}
for j_str in df_sample["data_json"]:
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
    fill_rate = (nn / total) * 100
    active_rate = (nz / total) * 100
    rows.append({
        "Key": k,
        "Fill Rate (%)": round(fill_rate, 2),
        "Active (Non-Zero) Rate (%)": round(active_rate, 2),
        "Total Counted": total
    })

df_res = pd.DataFrame(rows).sort_values(by="Fill Rate (%)", ascending=False)
print("\n" + "=" * 90)
print("AUDIT RESULTS: FILL RATE & VALUE SPARSITY ACROSS 60 RATIO KEYS")
print("=" * 90)
print(df_res.to_string(index=False))
