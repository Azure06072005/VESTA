import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_path = 'D:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

entries = data['log']['entries']

for idx in [311, 790, 865, 866]:
    if idx < len(entries):
        entry = entries[idx]
        url = entry['request']['url']
        resp = entry['response']
        text = resp.get('content', {}).get('text', '')
        print(f"==================================================")
        print(f"ENTRY #{idx}: {url}")
        try:
            js = json.loads(text)
            print("Keys:", list(js.keys()))
            if 'finance' in js:
                res = js['finance'].get('result', {})
                print("finance.result keys:", list(res.keys()) if isinstance(res, dict) else type(res))
                if isinstance(res, dict):
                    for rk, rv in res.items():
                        if isinstance(rv, list):
                            print(f"  {rk}: list of {len(rv)} items")
                            if len(rv) > 0:
                                print(f"    sample item {rk}[0]:", json.dumps(rv[0], indent=2)[:500])
            elif 'data' in js:
                d = js['data']
                print("data keys:", list(d.keys()))
                cds = d.get('cdsData', {})
                print("cdsData keys/type:", list(cds.keys()) if isinstance(cds, dict) else type(cds))
                if isinstance(cds, dict):
                    for ck, cv in cds.items():
                        if isinstance(cv, list):
                            print(f"  cds.{ck}: list of {len(cv)} items")
                            if len(cv) > 0:
                                print(f"    sample:", json.dumps(cv[0], indent=2)[:500])
                        elif isinstance(cv, dict):
                            print(f"  cds.{ck} keys:", list(cv.keys())[:10])
                            # check if modules or stream inside
                            for subk in ['modules', 'stream', 'items', 'content']:
                                if subk in cv:
                                    print(f"    subfield {subk}:", type(cv[subk]), len(cv[subk]) if isinstance(cv[subk], (list, dict)) else '')
                                    if isinstance(cv[subk], list) and len(cv[subk]) > 0:
                                        print(f"    sample subfield {subk}[0]:", json.dumps(cv[subk][0], indent=2)[:500])
        except Exception as e:
            print("Error parsing JSON:", e)
            print("Text preview:", text[:300])
