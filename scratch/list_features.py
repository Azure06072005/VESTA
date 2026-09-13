import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('Harness/feature_list.json', encoding='utf-8') as f:
    data = json.load(f)

for feat in data['features']:
    print(f"{feat['id']}: {feat['name']} [{feat['state']}]")
