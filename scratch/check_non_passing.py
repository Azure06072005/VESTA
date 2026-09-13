import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('Harness/feature_list.json', encoding='utf-8') as f:
    data = json.load(f)

features = data['features']
f104_idx = next(i for i, f in enumerate(features) if f['id'] == 'F104')
subset = features[:f104_idx]

print(f"Total features up to F104: {len(subset)}")
non_passing = [f for f in subset if f['state'] != 'passing']
print(f"Non-passing features count: {len(non_passing)}\n")

for f in non_passing:
    print(f"==================================================")
    print(f"ID: {f['id']}")
    print(f"Name: {f['name']}")
    print(f"State: {f['state']}")
    print(f"Dependencies: {f.get('dependencies', [])}")
    print(f"Behavior: {f.get('behavior', '')}")
    print(f"Verification: {f.get('verification', '')}")
    print(f"Evidence: {f.get('evidence', '')}")
    print()
