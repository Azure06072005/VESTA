import urllib.request
import urllib.parse
import http.cookiejar
import re
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Cookie jar to hold session cookies
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
}

# 1. GET page to get session cookie & verification token
page_url = 'https://finance.vietstock.vn/lich-su-kien.htm'
print(f"Step 1: Requesting {page_url}...")
req = urllib.request.Request(page_url, headers=headers)
try:
    with opener.open(req, timeout=10) as res:
        html = res.read().decode('utf-8', errors='ignore')
        print(f"  -> Page received: {len(html)} bytes")
except Exception as e:
    print(f"  -> Error GET page: {e}")
    sys.exit(1)

# Extract __RequestVerificationToken (can be unquoted: value=xyz>)
match_token = re.search(r'name=[\"\']?__RequestVerificationToken[\"\']?[^>]*value=[\"\']?([^\s\"\'>]+)', html)
token = match_token.group(1) if match_token else ""
print(f"Step 2: Token extracted: {token[:35]}... (length={len(token)})")

# 2. POST to https://finance.vietstock.vn/data/eventstypedata
api_url = 'https://finance.vietstock.vn/data/eventstypedata'
post_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': page_url,
    'Origin': 'https://finance.vietstock.vn'
}

params = {
    'eventTypeID': '1',        # Cổ tức, thưởng và phát hành thêm
    'channelID': '0',          # Tất cả các kênh (tiền mặt, cổ phiếu, phát hành thêm...)
    'code': 'FPT',             # Lọc thử cho mã FPT
    'catID': '-1',             # Tất cả các sàn
    'fDate': '2020-01-01',
    'tDate': '2026-12-31',
    'page': '1',
    'pageSize': '20',
    'orderBy': 'Date1',
    'orderDir': 'DESC',
    '__RequestVerificationToken': token
}

encoded_data = urllib.parse.urlencode(params).encode('utf-8')
post_req = urllib.request.Request(api_url, data=encoded_data, headers=post_headers)

print(f"\nStep 3: POST to {api_url} for FPT...")
try:
    with opener.open(post_req, timeout=10) as res:
        raw_bytes = res.read()
        resp_data = raw_bytes.decode('utf-8-sig', errors='ignore')
        print(f"  -> Status {res.getcode()}, Response length: {len(resp_data)} bytes")
        try:
            parsed = json.loads(resp_data)
            events_list = parsed[0] if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], list) else parsed
            if isinstance(events_list, list):
                print(f"  -> Successfully received {len(events_list)} events for FPT!")
                for idx, item in enumerate(events_list[:10], 1):
                    code = item.get('Code')
                    name = item.get('Name')
                    note = item.get('Note')
                    gdkhq = item.get('GDKHQDate')
                    payment = item.get('Time')
                    print(f"    [{idx}] {code} | {name} | {note}")
                    print(f"        GDKHQ: {gdkhq} | Payment Date: {payment}")
            if len(parsed) > 1:
                print("  -> Summary metadata:", parsed[1])
        except Exception as json_err:
            print(f"  -> JSON decode error: {json_err}, Snippet: {resp_data[:300]}")
except Exception as e:
    print(f"  -> Error POST API: {e}")
