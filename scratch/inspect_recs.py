import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('Harness/feature_list.json', encoding='utf-8') as f:
    data = json.load(f)

print("=== DETAILED F1** FEATURES ===")
for feat in data.get('features', []):
    fid = feat.get('id', '')
    if fid.startswith('F1'):
        print(f"\n[{fid}] {feat.get('name')}")
        print(f"State: {feat.get('state')}")
        print(f"Behavior: {feat.get('behavior')[:200]}...")
        print(f"Recommendations:")
        for r in feat.get('recommendation', []):
            print(f"  * {r}")
