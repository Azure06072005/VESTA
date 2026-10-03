import json

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data.get('features', [])

with open('scratch/f0_f2_audit_summary.txt', 'w', encoding='utf-8') as out:
    out.write(f"Total features in list: {len(features)}\n\n")

    for item in features:
        fid = item.get('id', '')
        if fid.startswith(('F0', 'F1', 'F2')):
            name = item.get('name', '')
            pros = item.get('pros', [])
            cons = item.get('cons', [])
            recs = item.get('recommendation', [])
            state = item.get('state', '')
            evidence = item.get('evidence', '')
            if pros or cons or recs:
                out.write(f"=== {fid} [{state}]: {name} ===\n")
                for p in pros:
                    out.write(f"  [PRO] {p}\n")
                for c in cons:
                    out.write(f"  [CON] {c}\n")
                for r in recs:
                    out.write(f"  [REC] {r}\n")
                out.write("\n")
