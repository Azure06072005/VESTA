import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import urllib.request
import json

res = urllib.request.urlopen('http://127.0.0.1:8899/api/status')
d = json.loads(res.read().decode('utf-8'))
print('total tables:', len(d.get('tables', [])))
for t in d.get('tables', []):
    print(f"- {t['name']}: {t['records']:,} rows | max_date={t['max_date']} | status={t['status']}")
