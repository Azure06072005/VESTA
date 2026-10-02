import json
import urllib.request
import sys
sys.stdout.reconfigure(encoding='utf-8')

url = "https://trading.vietcap.com.vn/api/price/symbols/getList"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn/",
}

payload = json.dumps({"symbols": ["FPT", "SSI", "HPG", "VCB"]}).encode("utf-8")
req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print(f"Gọi Vietcap API thành công! Nhận được {len(data)} items.")
    for item in data[:2]:
        sym = item.get("listingInfo", {}).get("symbol")
        print(f"\n--- Mã: {sym} ---")
        print("listingInfo keys:", list(item.get("listingInfo", {}).keys()))
        print("matchPrice:", item.get("matchPrice"))
        print("bidAsk:", item.get("bidAsk"))
except Exception as e:
    print("Lỗi khi gọi Vietcap API:", e)
