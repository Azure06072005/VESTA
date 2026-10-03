import json
import os

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data.get('features', [])
print(f"Total features: {len(features)}")

for feat in features:
    fid = feat.get('id')
    name = feat.get('name')
    verif = feat.get('verification', '')
    run_cmd = feat.get('run_command')
    test_cmd = feat.get('test_command')
    print(f"[{fid}] {name}")
    print(f"  Existing run_command: {run_cmd}")
    print(f"  Existing test_command: {test_cmd}")
    print(f"  Verification: {verif[:80]}...")
