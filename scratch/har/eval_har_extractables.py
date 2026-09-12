import json
import os
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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

print(f"Total existing unique URLs across all tables & dbs: {len(seen_urls):,}")

har_base = Path("scratch/har")

def extract_from_soup(soup, site_key):
    extracted = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)
        if len(title) < 25:
            continue
            
        # Site-specific rules
        if site_key == "tinnhanhchungkhoan":
            if "tinnhanhchungkhoan.vn" in href or href.startswith("/"):
                if re.search(r"-\d+\.html|post\d+", href) or ("/chung-khoan/" in href or "/doanh-nghiep/" in href or "/tai-chinh/" in href or "/vi-mo/" in href or "/dia-oc/" in href):
                    full_url = f"https://tinnhanhchungkhoan.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "thoibaotaichinh":
            if "thoibaotaichinhvietnam.vn" in href or href.startswith("/"):
                if any(k in href for k in ["/chung-khoan/", "/tai-chinh/", "/kinh-te/", "/doanh-nghiep/", "/ngan-hang/", "/thue-hai-quan/", "/dau-tu/"]):
                    full_url = f"https://thoibaotaichinhvietnam.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "thoibaonganhang":
            if "thoibaonganhang.vn" in href or href.startswith("/"):
                if re.search(r"-\d+\.html", href) and not any(k in href for k in ["/video/", "/media/", "/podcast/"]):
                    full_url = f"https://thoibaonganhang.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "nguoiquansat":
            if "nguoiquansat.vn" in href or href.startswith("/"):
                if not any(k in href for k in ["/tag/", "/video/", "/media/"]) and (re.search(r"-\d+\.html|-d\d+", href) or "/kinh-doanh/" in href or "/chung-khoan/" in href or "/tai-chinh/" in href or "/doanh-nghiep/" in href):
                    full_url = f"https://nguoiquansat.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "nhandan":
            if "nhandan.vn" in href or href.startswith("/"):
                if not any(k in href for k in ["/tag/", "/video/", "/media/", "/photo/"]) and (re.search(r"-\d+\.html|post\d+", href) or "/kinhte/" in href or "/chungkhoan/" in href or "/tphcm/" in href):
                    full_url = f"https://nhandan.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "vietnamfinance":
            if "vietnamfinance.vn" in href or href.startswith("/"):
                if ("-d" in href or href.endswith(".html")) and not any(k in href for k in ["/tag/", "/video/", "/media/"]):
                    full_url = f"https://vietnamfinance.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "vneconomy":
            if "vneconomy.vn" in href or href.startswith("/"):
                if href.endswith(".htm") and not any(k in href for k in ["/tag/", "/video/", "/magazine/"]):
                    full_url = f"https://vneconomy.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "tienphong":
            if "tienphong.vn" in href or href.startswith("/"):
                if href.endswith(".tpo") and not any(k in href for k in ["/tag/", "/video/", "/media/"]):
                    full_url = f"https://tienphong.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "tuoitre":
            if "tuoitre.vn" in href or href.startswith("/"):
                if href.endswith(".htm") and not any(k in href for k in ["/tag/", "/video/", "/media/"]):
                    full_url = f"https://tuoitre.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "vietstock":
            if "vietstock.vn" in href or href.startswith("/"):
                if (href.endswith(".htm") or "/2026/" in href or "/2025/" in href) and not any(k in href for k in ["/tag/", "/video/"]):
                    full_url = f"https://vietstock.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "cafef":
            if "cafef.vn" in href or href.startswith("/"):
                if (href.endswith(".chn") or href.endswith(".htm")) and not any(k in href for k in ["/tag/", "/video/"]):
                    full_url = f"https://cafef.vn{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
        elif site_key == "yahoo_finance":
            if "finance.yahoo.com" in href or href.startswith("/"):
                if "/news/" in href:
                    full_url = f"https://finance.yahoo.com{href}" if href.startswith("/") else href
                    extracted.append((full_url, title))
    return extracted

stats = {}

for folder in sorted(har_base.iterdir()):
    if not folder.is_dir():
        continue
    site_key = folder.name
    har_files = list(folder.glob("*.har"))
    
    site_found = {}
    for hf in har_files:
        try:
            with open(hf, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            entries = data.get("log", {}).get("entries", [])
            for e in entries:
                text = e.get("response", {}).get("content", {}).get("text", "")
                if text and len(text) > 1000:
                    soup = BeautifulSoup(text, "html.parser")
                    items = extract_from_soup(soup, site_key)
                    for u, t in items:
                        if u not in site_found:
                            site_found[u] = t
        except Exception as ex:
            pass
            
    total_scraped = len(site_found)
    new_items = {u: t for u, t in site_found.items() if u not in seen_urls}
    stats[site_key] = {
        "har_files": len(har_files),
        "total_in_har": total_scraped,
        "already_in_db": total_scraped - len(new_items),
        "NEW_UNINGESTED": len(new_items)
    }

print("\n" + "=" * 75)
print(f"{'SITE':<22} | {'HARS':<5} | {'IN HAR':<8} | {'IN DB':<8} | {'NEW UNINGESTED':<15}")
print("=" * 75)
tot_new = 0
for s, st in stats.items():
    tot_new += st['NEW_UNINGESTED']
    print(f"{s:<22} | {st['har_files']:<5} | {st['total_in_har']:<8} | {st['already_in_db']:<8} | {st['NEW_UNINGESTED']:<15}")
print("-" * 75)
print(f"TOTAL NEW UNINGESTED ARTICLES FROM HARs: {tot_new:,}")
