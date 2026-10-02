import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
data = json.load(open('Harness/feature_list.json', encoding='utf-8'))
for f in data['features']:
    print(f"{f['id']}: {f['name'][:50]} [{f['state']}]")
