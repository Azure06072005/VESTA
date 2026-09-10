import requests
import sys

sys.stdout.reconfigure(encoding='utf-8')

headers_real = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
}

for url in [
    "https://luatvietnam.vn/tin-phap-luat.html",
    "https://luatvietnam.vn/van-ban-moi.html",
    "https://luatvietnam.vn/chung-khoan-35-f1.html"
]:
    r = requests.get(url, headers=headers_real, timeout=10)
    print(f"{url} -> status {r.status_code}, length {len(r.text)}, is_cf: {'Cloudflare' in r.text or 'Attention Required' in r.text}")
