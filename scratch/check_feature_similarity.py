import json
from collections import defaultdict

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

features = d.get('features', [])

# Check 1: verification commands
verif_map = defaultdict(list)
for f in features:
    v = f.get('verification', '').strip()
    if v:
        verif_map[v].append(f['id'])

dup_verifs = {k: v for k, v in verif_map.items() if len(v) > 1}

# Check 2: test_command
test_cmd_map = defaultdict(list)
for f in features:
    tc = f.get('test_command', '').strip()
    if tc:
        test_cmd_map[tc].append(f['id'])

dup_test_cmds = {k: v for k, v in test_cmd_map.items() if len(v) > 1}

# Check 3: run_command
run_cmd_map = defaultdict(list)
for f in features:
    rc = f.get('run_command', '').strip()
    if rc:
        run_cmd_map[rc].append(f['id'])

dup_run_cmds = {k: v for k, v in run_cmd_map.items() if len(v) > 1}

print("Duplicate Verifications:", dup_verifs)
print("Duplicate Test Commands:", dup_test_cmds)
print("Duplicate Run Commands:", dup_run_cmds)
