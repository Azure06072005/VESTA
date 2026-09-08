import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

har_path = 'd:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har'
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

count = 0
for idx, e in enumerate(data['log']['entries']):
    u = e['request']['url']
    if 'nexus-gateway-prod.media.yahoo.com' in u and e['request']['method'] == 'POST':
        resp_text = e['response'].get('content', {}).get('text', '')
        if len(resp_text) > 1000:
            count += 1
            print(f"\n==================================================")
            print(f"GraphQL Entry #{idx} (Response Size: {len(resp_text)})")
            # Request postData
            post_data = e['request'].get('postData', {}).get('text', '')
            print("Request Payload (first 500 chars):")
            print(post_data[:500])
            
            # Response preview
            try:
                js = json.loads(resp_text)
                print("Response Root Keys:", list(js.keys()))
                if 'data' in js and js['data']:
                    print("  data keys:", list(js['data'].keys()))
                    for dk, dv in js['data'].items():
                        if isinstance(dv, dict):
                            print(f"    data.{dk} keys:", list(dv.keys()))
                            # check if main/stream or edges
                            main = dv.get('main') or dv
                            if isinstance(main, dict):
                                if 'stream' in main:
                                    stream = main['stream']
                                    print(f"      FOUND STREAM of {len(stream)} items!")
                                    if len(stream) > 0:
                                        s0 = stream[0]
                                        print("      Sample stream item:", json.dumps(s0, indent=2)[:400])
                                elif 'edges' in main:
                                    edges = main['edges']
                                    print(f"      FOUND EDGES of {len(edges)} items!")
                                    if len(edges) > 0:
                                        print("      Sample edge item:", json.dumps(edges[0], indent=2)[:400])
            except Exception as ex:
                print("Error parsing response JSON:", ex)
                
            if count >= 3:
                break
