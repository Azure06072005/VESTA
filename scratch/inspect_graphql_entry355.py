import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_path = 'd:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

e355 = data['log']['entries'][355]
req = e355['request']
print("URL:", req['url'])
print("Method:", req['method'])
print("Headers:")
headers_dict = {}
for h in req['headers']:
    headers_dict[h['name']] = h['value']
    if not h['name'].startswith(':'):
        print(f"  {h['name']}: {h['value']}")

post_text = req.get('postData', {}).get('text', '')
post_json = json.loads(post_text)
print("\nOperationName:", post_json.get('operationName'))
print("Variables:\n", json.dumps(post_json.get('variables'), indent=2))
print("\nQuery preview:\n", post_json.get('query')[:300])

# Also check response stream item in full detail
resp_json = json.loads(e355['response']['content']['text'])
stream = resp_json['data']['lightyearList']['main']['stream']
print(f"\nTotal stream items in entry #355: {len(stream)}")
print("Item 0 full details:\n", json.dumps(stream[0], indent=2))
