import urllib.request
import json
import ssl

api_key = "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"
url = f"https://vnstocks.com/api/vnstock/license/verify?api_key={api_key}&device_id=vibe-setup"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    url,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
)

try:
    with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
        data = json.loads(response.read().decode())
        print("=== VNSTOCK LICENSE VERIFICATION ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print("Error verifying license:", e)
