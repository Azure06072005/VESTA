"""scratch/check_features_status.py

Inspects Harness/feature_list.json statuses
"""
import sys
import json
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

data = json.load(open("Harness/feature_list.json", encoding="utf-8"))
feats = data["features"]
print("Total Features:", len(feats))
print("Status Counts:", Counter([f["state"] for f in feats]))

print("\nNon-passing Features:")
for f in feats:
    if f["state"] != "passing":
        print(f" - [{f['state'].upper():<12}] {f['id']:<10} : {f['name']}")
