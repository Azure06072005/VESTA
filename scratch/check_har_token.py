import json
import re

with open('scratch/har/vietstock/lich_su_kien.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

for e in data.get('log', {}).get('entries', []):
    url = e.get('request', {}).get('url', '')
    if 'lich-su-kien.htm' in url:
        print(f"Found request: {url}")
        res = e.get('response', {})
        text = res.get('content', {}).get('text', '')
        print(f"Response len: {len(text)}")
        
        # Check inputs
        for inp in re.findall(r'<input[^>]+>', text):
            if 'token' in inp.lower():
                print("  Input:", inp)
        
        # Check cookies
        req_cookies = e.get('request', {}).get('cookies', [])
        res_cookies = e.get('response', {}).get('cookies', [])
        print("  Req cookies:", [(c.get('name'), c.get('value')[:30]) for c in req_cookies])
        print("  Res cookies:", [(c.get('name'), c.get('value')[:30]) for c in res_cookies])

    if 'eventstypedata' in url:
        print(f"\nFound eventstypedata request: {url}")
        req_cookies = e.get('request', {}).get('cookies', [])
        print("  eventstypedata Req cookies:", [(c.get('name'), c.get('value')[:30]) for c in req_cookies])
        post_data = e.get('request', {}).get('postData', {}).get('text', '')
        print("  eventstypedata POST body:", post_data[:200])
