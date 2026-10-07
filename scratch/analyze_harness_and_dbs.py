import json
import duckdb
import os
import sys

def analyze_features():
    path = "d:/VESTA/Harness/feature_list.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    features = data.get("features", [])
    print(f"Total features: {len(features)}")
    
    tiers = {}
    for feat in features:
        fid = feat.get("id", "")
        tier = fid[:2] if len(fid)>=2 else "other"
        if fid.startswith("F0") and len(fid)>=4:
            # could be F00x, F05x, F07x
            num = int(fid[1:4]) if fid[1:4].isdigit() else 0
            if num < 50:
                tier = "F0xx (Core Crawlers)"
            elif num < 73:
                tier = "F05x (Auxiliary / Enhancers / Macro)"
            else:
                tier = "F07x (Multi-Asset Crawlers)"
        elif fid.startswith("F1"):
            tier = "F1xx (Validation / PIT / Preprocessing)"
        elif fid.startswith("F2"):
            tier = "F2xx (Hypothesis Testing / Stat Gates)"
        elif fid.startswith("F3"):
            tier = "F3xx (Deep Learning / PhoBERT / Multimodal / SLM)"
        elif fid.startswith("F4"):
            tier = "F4xx (Serving / Monitoring / Continuous Retraining)"
        elif fid.startswith("F5"):
            tier = "F5xx (Multi-Bot Strategy Arena)"
        elif fid.startswith("F9"):
            tier = "F9xx (Broker Compliance & Execution - Blocked)"
        else:
            tier = "Other"
            
        tiers.setdefault(tier, []).append(feat)

    print("\n--- Summary by Tier ---")
    for t_name, f_list in tiers.items():
        states = {}
        for f in f_list:
            st = f.get("state", "unknown")
            states[st] = states.get(st, 0) + 1
        print(f"{t_name}: {len(f_list)} features -> {states}")

    return tiers, features

if __name__ == "__main__":
    analyze_features()
