import duckdb
import json
import urllib.request
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
vn100 = [r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.dim_index_constituents WHERE index_code = 'VN100' ORDER BY symbol").fetchall()]
con.close()

print(f"Danh sách rổ VN100 ({len(vn100)} mã)")

url = 'https://trading.vietcap.com.vn/api/price/symbols/getList'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'Referer': 'https://trading.vietcap.com.vn/',
    'Origin': 'https://trading.vietcap.com.vn/',
}

# Chia batch 25 mã mỗi request
chunk_size = 25
all_data = []

for i in range(0, len(vn100), chunk_size):
    batch = vn100[i:i+chunk_size]
    payload = json.dumps({'symbols': batch}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            batch_data = json.loads(resp.read().decode('utf-8'))
            all_data.extend(batch_data)
            print(f"  Batch {i//chunk_size + 1}: Gửi {len(batch)} mã -> Nhận {len(batch_data)} mã thành công!")
    except Exception as e:
        print(f"  Lỗi batch {batch}: {e}")
    time.sleep(0.1)

print(f"\n🎉 TỔNG KẾT: Thu thập được {len(all_data)} mã từ Vietcap Direct API!")
