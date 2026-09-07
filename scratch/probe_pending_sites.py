import urllib.request
import urllib.error
import ssl
import socket
import yaml

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Quant-Crawler/2.1)'
}

with open('configs/robots_global.yaml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

pending_sites = []
for g, srcs in cfg.get('tier3_sources', {}).items():
    for k, v in srcs.items():
        if v.get('status') == 'PENDING':
            pending_sites.append((g, k, v.get('base_url'), v.get('sitemap_url')))

print(f"Total PENDING sites to probe: {len(pending_sites)}")
results = {}

for g, k, base_url, sitemap_url in pending_sites:
    target = sitemap_url or base_url
    if not target:
        results[k] = ("ERROR", "No URL provided")
        continue
    req = urllib.request.Request(target, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=7, context=ctx) as resp:
            code = resp.getcode()
            content_type = resp.headers.get('Content-Type', '')
            results[k] = ("OK", f"HTTP {code} ({content_type[:30]})")
    except urllib.error.HTTPError as e:
        results[k] = ("REJECTED", f"HTTP {e.code}")
    except urllib.error.URLError as e:
        results[k] = ("UNREACHABLE", str(e.reason)[:50])
    except Exception as e:
        results[k] = ("ERROR", str(e)[:50])

print("\n=== PROBE RESULTS ===")
for g, k, base_url, sitemap_url in pending_sites:
    st, msg = results.get(k, ("UNKNOWN", ""))
    print(f"[{g:25s}] {k:20s} -> {st:11s} : {msg}")
