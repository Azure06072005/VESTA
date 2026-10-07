import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
with open('d:/VESTA/Harness/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for feat in data['features']:
    if feat['id'] in ('F305', 'F501', 'F502'):
        print(f"=== {feat['id']}: {feat['name']} ===")
        print("Behavior:", feat.get('behavior'))
        print("Evidence:", feat.get('evidence'))
        print("State:", feat.get('state'))
        print("Pros:", feat.get('pros'))
        print("Cons:", feat.get('cons'))
        print("Rec:", feat.get('recommendation'))
        print()
