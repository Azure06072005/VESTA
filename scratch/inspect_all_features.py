import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data.get('features', [])
print(f"Total features: {len(features)}")

for feat in features:
    fid = feat.get('id')
    name = feat.get('name')
    verif = feat.get('verification', '')
    file_deps = feat.get('file_dependencies', [])
    print(f"{fid} | {name} | file_deps_len: {len(file_deps)}")
