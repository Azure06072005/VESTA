import json
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')

operations = set()
slugs = set()
list_names = set()

for har in glob.glob('d:/VESTA/scratch/har/yahoo_finance/*.har'):
    with open(har, 'r', encoding='utf-8', errors='ignore') as f:
        data = json.load(f)
    for e in data['log']['entries']:
        post_data = e['request'].get('postData', {}).get('text', '')
        if post_data and post_data.strip().startswith('{'):
            try:
                js = json.loads(post_data)
                if 'operationName' in js:
                    operations.add(js['operationName'])
                vars_ = js.get('variables', {})
                if 'listInput' in vars_:
                    li = vars_['listInput']
                    if 'slug' in li:
                        slugs.add(li['slug'])
                    if 'uuid' in li:
                        slugs.add(f"uuid:{li['uuid']}")
                if 'listName' in vars_:
                    list_names.add(vars_['listName'])
            except Exception:
                pass

print("Discovered GraphQL Operation Names:")
for op in sorted(operations):
    print("  *", op)

print("\nDiscovered Slugs / List IDs:")
for s in sorted(slugs):
    print("  *", s)

print("\nDiscovered List Names:")
for ln in sorted(list_names):
    print("  *", ln)
