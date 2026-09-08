import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('D:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

e311 = data['log']['entries'][311]
req = e311['request']
print("URL:", req['url'])
print("Method:", req['method'])
print("Headers:")
for h in req['headers']:
    print(f"  {h['name']}: {h['value']}")

print("\nCookies:")
for c in req['cookies']:
    print(f"  {c['name']}: {c['value'][:30]}...")

# Also check Entry 866 and Entry 314
print("\n--- Entry 314 (Crumb request) ---")
e314 = data['log']['entries'][314]
for h in e314['request']['headers']:
    print(f"  {h['name']}: {h['value']}")
