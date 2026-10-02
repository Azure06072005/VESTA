import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with open('Harness/feature_list.json', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total features: {len(data['features'])}")
print(f"{'ID':7s} | {'State':12s} | Name")
print("-" * 80)
for feat in data['features']:
    fid = feat['id']
    if fid.startswith('F0') or fid in ['F095', 'F096', 'F097', 'F098', 'F099', 'F100', 'F101']:
        print(f"{feat['id']:7s} | {feat['state']:12s} | {feat['name']}")
