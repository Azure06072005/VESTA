import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data['features']
group1 = [] # F000 -> F007b
group2 = [] # F008, F009
group3 = [] # F050 -> F072
group4 = [] # F101+

for feat in features:
    fid = feat['id']
    if fid.startswith('F05') or fid.startswith('F06') or fid.startswith('F07'):
        group3.append(feat)
    elif fid in ['F008', 'F009']:
        group2.append(feat)
    elif fid.startswith('F1') or fid.startswith('F2') or fid.startswith('F3') or fid.startswith('F4') or fid.startswith('F5') or fid.startswith('F9'):
        group4.append(feat)
    else:
        group1.append(feat)

print(f"Group 1 (F000-F007b): {len(group1)} items: {[x['id'] for x in group1]}")
print(f"Group 3 (F05*-F07*):  {len(group3)} items: {[x['id'] for x in group3]}")
print(f"Group 2 (F008-F009):  {len(group2)} items: {[x['id'] for x in group2]}")
print(f"Group 4 (F101+):      {len(group4)} items: {[x['id'] for x in group4]}")

reordered = group1 + group3 + group2 + group4
print(f"Total before: {len(features)}, Total after: {len(reordered)}")
assert len(features) == len(reordered), "Số lượng features không khớp!"

# Cập nhật dependencies của F008 và F009 nếu cần thiết
for feat in group2:
    if feat['id'] == 'F008':
        feat['behavior'] += " (Extended to coordinate retries for both micro F0xx and auxiliary macro F05x crawlers via meta.crawl_progress)."
    elif feat['id'] == 'F009':
        # Bổ sung dependency F072 để F009 là checkpoint cuối cùng của toàn bộ tầng Data Ingestion
        if 'F072' not in feat['dependencies']:
            feat['dependencies'].append('F072')

# Cập nhật comment trong feature_list.json
add_comment = (
    "\n\nRE-SEQUENCING (2026-09-28):\n"
    "6. Re-ordered F05* (Auxiliary Macro Crawlers F050-F072) ahead of F008 (Retry/Reconciliation module) "
    "and F009 (Tier Checkpoint). This enables F008 and F009 to act as the unified retry coordinator and "
    "reconciliation gate for BOTH micro crawlers (F001-F007b) and macro/sector crawlers (F050-F072)."
)
data['_comment'] = data['_comment'] + add_comment
data['features'] = reordered

with open('Harness/feature_list.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("SUCCESSFULLY REORDERED feature_list.json!")
