import json

data = json.loads(open("scratch/db_comparison_results.json", encoding="utf-8").read())

print(f"--- TABLES ONLY IN VESTA ({len(data['only_in_canonical'])}) ---")
for t in data['only_in_canonical']:
    print(f"  {t['table']}: {t['rows']:,} rows, {t['cols']} cols")

print(f"\n--- TABLES ONLY IN SNAPSHOT ({len(data['only_in_snapshot'])}) ---")
for t in data['only_in_snapshot']:
    print(f"  {t['table']}: {t['rows']:,} rows, {t['cols']} cols")

print(f"\n--- COMMON TABLES ({len(data['common'])}) ---")
print(f"{'Table':<35} | {'Vesta Rows':>12} | {'Snap Rows':>12} | {'Delta':>12} | {'Vesta Dates':<23} | {'Snap Dates':<23} | {'Syms (V/S)':<10}")
print("-" * 135)

# Group by category / schema
for c in sorted(data['common'], key=lambda x: (x['schema'], x['name'])):
    tbl = c['table']
    r_v = f"{c['rows_vesta']:,}" if c['rows_vesta'] is not None else "N/A"
    r_s = f"{c['rows_snapshot']:,}" if c['rows_snapshot'] is not None else "N/A"
    delta = f"{c['delta']:+,}" if c['delta'] is not None else "N/A"
    
    dates_v = f"{c.get('c_min_date', '')[:10]}..{c.get('c_max_date', '')[:10]}" if 'c_min_date' in c and c['c_min_date'] else "N/A"
    dates_s = f"{c.get('s_min_date', '')[:10]}..{c.get('s_max_date', '')[:10]}" if 's_min_date' in c and c['s_min_date'] else "N/A"
    
    syms = f"{c.get('c_syms', '-')}/{c.get('s_syms', '-')}"
    
    print(f"{tbl:<35} | {r_v:>12} | {r_s:>12} | {delta:>12} | {dates_v:<23} | {dates_s:<23} | {syms:<10}")
    if c['col_only_in_vesta'] or c['col_only_in_snapshot'] or c['type_diff']:
        print(f"    -> Schema diff: only_v={c['col_only_in_vesta']}, only_s={c['col_only_in_snapshot']}, type_diff={c['type_diff']}")
