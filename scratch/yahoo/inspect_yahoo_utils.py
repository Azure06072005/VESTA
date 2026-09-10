import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('d:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-main_page.har', 'r', encoding='utf-8', errors='ignore') as f:
    data = json.load(f)

for e in data['log']['entries']:
    if 'utils.Wjs3O4Mi.js' in e['request']['url']:
        txt = e['response'].get('content', {}).get('text', '')
        print("=== utils.Wjs3O4Mi.js Content length:", len(txt))
        # Find fetch or axios calls in utils
        import re
        urls = re.findall(r'https?://[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.~!*\'();:@&=+$,/?#\[\]-]*)?', txt)
        print("Discovered URLs in utils:")
        for u in set(urls):
            print("  *", u)
        
        # Search for graphql or api endpoint
        for match in re.finditer(r'(?:graphql|query1\.finance|api|xhr|fetch\(|path:)', txt, re.IGNORECASE):
            s = max(0, match.start() - 50)
            e_idx = min(len(txt), match.end() + 150)
            print("--- Snippet ---")
            print(txt[s:e_idx])
            break
