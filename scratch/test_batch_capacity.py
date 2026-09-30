import sys
import urllib.request
import json
import duckdb
import time

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
all_syms = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol WHERE exchange != 'DELISTED'").fetchall()]
con.close()

headers = {
    'User-Agent': 'Mozilla/5.0',
    'Content-Type': 'application/json',
    'Referer': 'https://trading.vietcap.com.vn/',
    'Origin': 'https://trading.vietcap.com.vn/',
}
url = 'https://trading.vietcap.com.vn/api/price/symbols/getList'

t0 = time.time()
payload_all = json.dumps({'symbols': all_syms}).encode('utf-8')
req_all = urllib.request.Request(url, data=payload_all, headers=headers, method='POST')
with urllib.request.urlopen(req_all, timeout=20) as r:
    data_all = json.loads(r.read())
elapsed = time.time() - t0
print(f'Test ALL: sent {len(all_syms)} active symbols, received {len(data_all)} items in a SINGLE request in {elapsed:.2f}s!')
