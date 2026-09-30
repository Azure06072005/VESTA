import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('scratch/vesta_news_schema_audit.json', encoding='utf-8') as f:
    d = json.load(f)

for k, v in sorted(d.items()):
    if k.startswith('core.'):
        print(f"=== {k}: {v['rows']:,} rows ===")
        for col in v['columns']:
            print(f"   {col['column']:<18} {col['type']:<12} nulls: {col['null_count']:,} ({col['pct_null']})")
        print()
