import json
import re
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

features = data.get('features', [])

for feat in features:
    fid = feat['id']
    name = feat['name']
    verif = feat.get('verification', '')
    file_deps = feat.get('file_dependencies', [])
    
    # Try to extract pytest command from verification
    pytest_match = re.search(r'(pytest\s+[^\n\r;&]+|python\s+-[^\n\r;&]+)', verif)
    verif_cmd = pytest_match.group(1).strip() if pytest_match else "N/A"
    
    src_files = [f for f in file_deps if f.startswith('src/')]
    test_files = [f for f in file_deps if f.startswith('tests/')]
    
    print(f"ID: {fid}")
    print(f"  Name: {name}")
    print(f"  Verif cmd: {verif_cmd}")
    print(f"  Src files: {src_files}")
    print(f"  Test files: {test_files}")
