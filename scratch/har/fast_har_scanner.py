import json
import os
import re
import sys
import time
from pathlib import Path
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

t0 = time.time()

# Load all known URLs across databases
seen_urls = set()
for db_path in ["db/crawlers_staging.duckdb", "db/vesta_latest_backup.duckdb", "db/vesta.duckdb"]:
    if os.path.exists(db_path):
        try:
            con = duckdb.connect(db_path, read_only=True)
            for schema, tbl in [("core", "macro_policy"), ("staging", "macro_policy"), ("core", "news"), ("staging", "news")]:
                try:
                    for row in con.execute(f"SELECT source_url FROM {schema}.{tbl}").fetchall():
                        if row[0]:
                            seen_urls.add(row[0].strip())
                except Exception:
                    pass
            con.close()
        except Exception:
            pass

print(f"Loaded {len(seen_urls):,} known URLs from DuckDB databases ({time.time()-t0:.2f}s).")

har_base = Path("scratch/har")

A_TAG_REGEX = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TAG_STRIP_REGEX = re.compile(r'<[^>]+>')

site_matchers = {
    "tinnhanhchungkhoan": (
        lambda href: ("tinnhanhchungkhoan.vn" in href or href.startswith("/")) and 
                     (bool(re.search(r"-\d+\.html|post\d+", href)) or any(k in href for k in ["/chung-khoan/", "/tai-chinh/", "/vi-mo/", "/dia-oc/"])),
        "https://www.tinnhanhchungkhoan.vn"
    ),
    "thoibaotaichinh": (
        lambda href: ("thoibaotaichinhvietnam.vn" in href or href.startswith("/")) and 
                     bool(re.search(r"-\d+\.html", href)) and not any(k in href for k in ["/video/", "/media/", "/photo/"]),
        "https://thoibaotaichinhvietnam.vn"
    ),
    "thoibaonganhang": (
        lambda href: ("thoibaonganhang.vn" in href or href.startswith("/")) and 
                     bool(re.search(r"-\d+\.html", href)) and not any(k in href for k in ["/video/", "/media/", "/podcast/"]),
        "https://thoibaonganhang.vn"
    ),
    "nguoiquansat": (
        lambda href: ("nguoiquansat.vn" in href or href.startswith("/")) and 
                     not any(k in href for k in ["/tag/", "/video/", "/media/"]) and (bool(re.search(r"-\d+\.html|-d\d+", href)) or any(k in href for k in ["/kinh-doanh/", "/chung-khoan/", "/tai-chinh/"])),
        "https://nguoiquansat.vn"
    ),
    "nhandan": (
        lambda href: ("nhandan.vn" in href or href.startswith("/")) and 
                     not any(k in href for k in ["/tag/", "/video/", "/media/", "/photo/"]) and (bool(re.search(r"-\d+\.html|post\d+", href)) or any(k in href for k in ["/kinhte/", "/chungkhoan/"])),
        "https://nhandan.vn"
    ),
    "vietnamfinance": (
        lambda href: ("vietnamfinance.vn" in href or href.startswith("/")) and 
                     ("-d" in href or href.endswith(".html")) and not any(k in href for k in ["/tag/", "/video/", "/media/"]),
        "https://vietnamfinance.vn"
    ),
    "vneconomy": (
        lambda href: ("vneconomy.vn" in href or href.startswith("/")) and 
                     href.endswith(".htm") and not any(k in href for k in ["/tag/", "/video/", "/magazine/"]),
        "https://vneconomy.vn"
    ),
    "tienphong": (
        lambda href: ("tienphong.vn" in href or href.startswith("/")) and 
                     href.endswith(".tpo") and not any(k in href for k in ["/tag/", "/video/", "/media/"]),
        "https://tienphong.vn"
    ),
    "tuoitre": (
        lambda href: ("tuoitre.vn" in href or href.startswith("/")) and 
                     href.endswith(".htm") and not any(k in href for k in ["/tag/", "/video/", "/media/"]),
        "https://tuoitre.vn"
    ),
    "vietstock": (
        lambda href: ("vietstock.vn" in href or href.startswith("/")) and 
                     (href.endswith(".htm") or "/2026/" in href or "/2025/" in href) and not any(k in href for k in ["/tag/", "/video/"]),
        "https://vietstock.vn"
    ),
    "cafef": (
        lambda href: ("cafef.vn" in href or href.startswith("/")) and 
                     (href.endswith(".chn") or href.endswith(".htm")) and not any(k in href for k in ["/tag/", "/video/"]),
        "https://cafef.vn"
    ),
    "yahoo_finance": (
        lambda href: ("finance.yahoo.com" in href or href.startswith("/")) and "/news/" in href,
        "https://finance.yahoo.com"
    ),
    "gdt": (
        lambda href: "gdt.gov.vn" in href or "wps/portal" in href or "wcm:path" in href,
        "https://www.gdt.gov.vn"
    ),
    "mof": (
        lambda href: "mof.gov.vn" in href or "/api/" in href or href.startswith("/"),
        "https://www.mof.gov.vn"
    )
}

stats = {}

for folder in sorted(har_base.iterdir()):
    if not folder.is_dir():
        continue
    site_key = folder.name
    har_files = list(folder.glob("*.har"))
    
    matcher, base_domain = site_matchers.get(site_key, (lambda h: True, ""))
    
    found_urls = set()
    
    for hf in har_files:
        try:
            with open(hf, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            entries = data.get("log", {}).get("entries", [])
            for e in entries:
                req_url = e.get("request", {}).get("url", "")
                resp = e.get("response", {})
                text = resp.get("content", {}).get("text", "")
                if not text:
                    continue
                # 1. Check direct JSON payloads (e.g. MOF, Tienphong morenews)
                if "json" in resp.get("content", {}).get("mimeType", ""):
                    # Scan for URL strings inside JSON
                    raw_urls = re.findall(r'https?://[^\s"\'<>]+', text)
                    for ru in raw_urls:
                        if matcher(ru):
                            found_urls.add(ru)
                # 2. Check HTML text using regex
                if len(text) > 500:
                    matches = A_TAG_REGEX.findall(text)
                    for href, inner_text in matches:
                        raw_title = TAG_STRIP_REGEX.sub("", inner_text).strip()
                        if len(raw_title) >= 20 and matcher(href):
                            if href.startswith("/"):
                                full_url = f"{base_domain}{href}"
                            elif href.startswith("http"):
                                full_url = href
                            else:
                                full_url = f"{base_domain}/{href}"
                            found_urls.add(full_url)
        except Exception:
            pass
            
    total_in_har = len(found_urls)
    new_urls = [u for u in found_urls if u not in seen_urls]
    stats[site_key] = {
        "har_files": len(har_files),
        "total_in_har": total_in_har,
        "already_in_db": total_in_har - len(new_urls),
        "new_uningested": len(new_urls)
    }

print("\n" + "=" * 80)
print(f"{'SITE KEY':<22} | {'HARs':<5} | {'IN HAR':<8} | {'IN DB':<8} | {'NEW UNINGESTED':<15}")
print("=" * 80)
total_new = 0
for s, st in stats.items():
    total_new += st['new_uningested']
    print(f"{s:<22} | {st['har_files']:<5} | {st['total_in_har']:<8} | {st['already_in_db']:<8} | {st['new_uningested']:<15}")
print("-" * 80)
print(f"TOTAL NEW UNINGESTED ARTICLES IN HAR FOLDER: {total_new:,}")
print(f"Total time taken: {time.time()-t0:.2f} seconds.")
