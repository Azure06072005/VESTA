import json
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')

for har in glob.glob('d:/VESTA/scratch/har/yahoo_finance/*.har'):
    with open(har, 'r', encoding='utf-8', errors='ignore') as f:
        data = json.load(f)
    print(f"\nChecking {har}...")
    for e in data['log']['entries']:
        u = e['request']['url']
        if any(k in u.lower() for k in ['graphql', 'nexus', 'lightyear', 'stream', 'polaris', 'visualization']):
            if not any(k in u.lower() for k in ['.js', '.css', '.png', '.jpg', '.svg']):
                method = e['request']['method']
                status = e['response']['status']
                size = len(e['response'].get('content', {}).get('text', ''))
                print(f"  {method} {u[:120]} (Status: {status}, Size: {size})")
