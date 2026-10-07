import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = "d:/VESTA/Harness/feature_list.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

features = data["features"]
print(f"Total features: {len(features)}")

out_data = []
for i, feat in enumerate(features):
    fid = feat.get("id", "")
    name = feat.get("name", "")
    state = feat.get("state", "")
    deps = feat.get("dependencies", [])
    file_deps = feat.get("file_dependencies", [])
    pros = feat.get("pros", "")
    cons = feat.get("cons", "")
    rec = feat.get("recommendation", "")
    behavior = feat.get("behavior", "")
    run_cmd = feat.get("run_command", "")
    test_cmd = feat.get("test_command", "")
    
    out_data.append({
        "index": i + 1,
        "id": fid,
        "name": name,
        "state": state,
        "dependencies": deps,
        "file_dependencies": file_deps,
        "pros": pros,
        "cons": cons,
        "recommendation": rec,
        "behavior": behavior,
        "run_command": run_cmd,
        "test_command": test_cmd
    })

with open("d:/VESTA/scratch/all_77_features_analyzed.json", "w", encoding="utf-8") as f:
    json.dump(out_data, f, ensure_ascii=False, indent=2)

print("Exported all 77 features to d:/VESTA/scratch/all_77_features_analyzed.json")
