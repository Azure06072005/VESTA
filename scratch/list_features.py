import json

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

lines = []
for f in d['features']:
    fid = f.get('id', '')
    state = f.get('state', '')
    name = f.get('name', '')
    lines.append(f"{fid} [{state}]: {name}")

with open('scratch/all_features.txt', 'w', encoding='utf-8') as out:
    out.write("\n".join(lines) + "\n")

print(f"Wrote {len(lines)} features to scratch/all_features.txt")
