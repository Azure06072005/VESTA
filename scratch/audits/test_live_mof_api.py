import urllib.request
import json
import ssl
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    "https://www.mof.gov.vn/api/article/reads?offset=0&limit=5",
    data=b'{"categoryId":"34c5a20a-5c6b-4012-89e7-65d718ea31dc"}',
    headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Quant-Crawler/2.1)"
    }
)
try:
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        print("HTTP Status:", resp.getcode())
        data = json.loads(resp.read().decode("utf-8"))
        print("Success:", data.get("success"))
        print("Total items available:", data.get("total"))
        print("Returned items:", len(data.get("data", [])))
        if data.get("data"):
            item = data["data"][0]
            print("Sample Title:", item.get("title"))
            print("Sample Date:", item.get("publicationTime"))
            print("Sample Slug:", item.get("slug"))
            print("Sample Desc:", item.get("description")[:100] if item.get("description") else None)
except Exception as e:
    print("Request error:", e)
