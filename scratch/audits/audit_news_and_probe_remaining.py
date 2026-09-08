import duckdb
import yaml
import urllib.request
import urllib.error
import ssl
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 1. Load database counts
con = duckdb.connect("d:/VESTA/db/vesta_latest_backup.duckdb", read_only=True)
news_counts = dict(con.execute("SELECT source, count(*) FROM core.news GROUP BY source").fetchall())
macro_counts = dict(con.execute("SELECT source, count(*) FROM core.macro_policy GROUP BY source").fetchall())
con.close()

# 2. Load YAML config
with open("configs/robots_global.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Quant-Crawler/2.1)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

print("=========================================================================")
print(">>> 1. AUDIT: TẤT CẢ CÁC NGUỒN TIN TỨC & VĨ MÔ ĐÃ CÀO TRONG DATABASE <<<")
print("=========================================================================")
print(f"Tổng bản ghi core.news: {sum(news_counts.values()):,} tin")
for s, c in sorted(news_counts.items(), key=lambda x: -x[1]):
    print(f"  - [core.news] {s:<20}: {c:,} bài viết")

print(f"\nTổng bản ghi core.macro_policy: {sum(macro_counts.values()):,} bài/văn bản")
for s, c in sorted(macro_counts.items(), key=lambda x: -x[1]):
    print(f"  - [core.macro_policy] {s:<20}: {c:,} văn bản/bài")

print("\n=========================================================================")
print(">>> 2. KIỂM TRA TOÀN BỘ CÁC NGUỒN ĐƯỢC KHAI BÁO TRONG ROBOTS_GLOBAL.YAML <<<")
print("=========================================================================")

all_sources = []
for group_name, group_srcs in cfg.get("tier3_sources", {}).items():
    for src_key, src_cfg in group_srcs.items():
        # Check if records exist in db
        db_count = macro_counts.get(src_key, 0) or news_counts.get(src_key, 0)
        status = src_cfg.get("status", "UNKNOWN")
        base_url = src_cfg.get("base_url") or src_cfg.get("url") or ""
        sitemap_url = src_cfg.get("sitemap_url") or ""
        all_sources.append({
            "group": group_name,
            "key": src_key,
            "name": src_cfg.get("name", src_key),
            "status": status,
            "db_count": db_count,
            "base_url": base_url,
            "sitemap_url": sitemap_url,
        })

crawled = [s for s in all_sources if s["db_count"] > 0]
not_crawled = [s for s in all_sources if s["db_count"] == 0]

print(f"Tổng số nguồn Tier 3: {len(all_sources)}")
print(f"  - Đã cào (db_count > 0): {len(crawled)} nguồn")
print(f"  - Chưa cào (db_count == 0): {len(not_crawled)} nguồn")

print("\n=========================================================================")
print(f">>> 3. PROBE KẾT NỐI {len(not_crawled)} NGUỒN CHƯA CÀO (BỎ QUA REJECT/UNREACHABLE) <<<")
print("=========================================================================")

reachable_sites = []
rejected_sites = []
unreachable_sites = []

for s in not_crawled:
    # Try sitemap_url first, then base_url
    urls_to_test = [u for u in [s["sitemap_url"], s["base_url"]] if u]
    if not urls_to_test:
        unreachable_sites.append((s, "NO_URL", "Không có URL"))
        continue
    
    success = False
    last_err_type = "UNKNOWN"
    last_err_msg = ""
    
    for test_url in urls_to_test:
        req = urllib.request.Request(test_url, headers=headers)
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                code = resp.getcode()
                c_type = resp.headers.get("Content-Type", "")
                dur = time.time() - t0
                reachable_sites.append((s, test_url, code, c_type, dur))
                success = True
                print(f"[REACHABLE]   {s['key']:<18} ({s['group']}) -> HTTP {code} ({dur:.2f}s) | {test_url}")
                break
        except urllib.error.HTTPError as e:
            last_err_type = "REJECTED"
            last_err_msg = f"HTTP {e.code} ({e.reason})"
        except urllib.error.URLError as e:
            last_err_type = "UNREACHABLE"
            last_err_msg = str(e.reason)[:45]
        except Exception as e:
            last_err_type = "UNREACHABLE"
            last_err_msg = str(e)[:45]
            
    if not success:
        if last_err_type == "REJECTED":
            rejected_sites.append((s, last_err_msg))
            print(f"[REJECTED]    {s['key']:<18} ({s['group']}) -> {last_err_msg}")
        else:
            unreachable_sites.append((s, last_err_type, last_err_msg))
            print(f"[UNREACHABLE] {s['key']:<18} ({s['group']}) -> {last_err_msg}")

print("\n=========================================================================")
print(">>> TỔNG HỢP KẾT QUẢ RÀ SOÁT <<<")
print("=========================================================================")
print(f"1. Số nguồn REACHABLE (Khả dụng, sẵn sàng cào): {len(reachable_sites)}")
for s, url, code, c_type, dur in reachable_sites:
    print(f"   * {s['key']:<18} | Nhóm: {s['group']:<25} | URL: {url}")

print(f"\n2. Số nguồn REJECTED (Bị chặn 403/Chống bot - BỎ QUA): {len(rejected_sites)}")
for s, msg in rejected_sites:
    print(f"   * {s['key']:<18} | {msg}")

print(f"\n3. Số nguồn UNREACHABLE (Lỗi DNS / Timeout / SSL - BỎ QUA): {len(unreachable_sites)}")
for s, err_type, msg in unreachable_sites:
    print(f"   * {s['key']:<18} | {msg}")
