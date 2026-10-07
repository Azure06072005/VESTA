import json

with open("d:/VESTA/scratch/all_77_features_analyzed.json", "r", encoding="utf-8") as f:
    features = json.load(f)

print(f"Total features: {len(features)}")

# Group by tier
tier_names = [
    ("Tier F0xx: Core Crawlers & Data Engineering", lambda fid: fid.startswith("F0") and int(fid[1:4]) < 50),
    ("Tier F05x: Auxiliary, Macro & Enhancers", lambda fid: fid.startswith("F0") and 50 <= int(fid[1:4]) < 73),
    ("Tier F07x: Multi-Asset Crawlers", lambda fid: fid.startswith("F0") and int(fid[1:4]) >= 73),
    ("Tier F1xx: Data Validation, PIT Joins & Feature Engineering", lambda fid: fid.startswith("F1")),
    ("Tier F2xx: Statistical Hypothesis Testing & Gatekeepers", lambda fid: fid.startswith("F2")),
    ("Tier F3xx: Deep Learning, PhoBERT, Cross-Attention & SLM", lambda fid: fid.startswith("F3")),
    ("Tier F4xx: Production Serving, Drift Telemetry & Retraining", lambda fid: fid.startswith("F4")),
    ("Tier F5xx: Multi-Bot Strategy Arena & Monte Carlo Simulation", lambda fid: fid.startswith("F5")),
    ("Tier F9xx: Broker Execution & Regulatory Compliance (Blocked)", lambda fid: fid.startswith("F9")),
]

for t_title, t_filter in tier_names:
    t_feats = [f for f in features if t_filter(f["id"])]
    print(f"\n=======================================================")
    print(f"{t_title} ({len(t_feats)} features)")
    print(f"=======================================================")
    for f in t_feats:
        print(f"  • [{f['id']}] {f['name']} | State: {f['state']}")
        print(f"      File Deps ({len(f['file_dependencies'])}): {', '.join(f['file_dependencies']) if f['file_dependencies'] else 'None explicit'}")
        print(f"      Pros: {f['pros'][:120]}..." if len(f['pros']) > 120 else f"      Pros: {f['pros']}")
        print(f"      Cons: {f['cons'][:120]}..." if len(f['cons']) > 120 else f"      Cons: {f['cons']}")
        print(f"      Rec:  {f['recommendation'][:120]}..." if len(f['recommendation']) > 120 else f"      Rec:  {f['recommendation']}")
