import duckdb
import yaml
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 1. Inspect both database files
db_files = ["db/vesta.duckdb", "db/vesta_latest_backup.duckdb"]
primary_db = "db/vesta_latest_backup.duckdb" if os.path.exists("db/vesta_latest_backup.duckdb") else "db/vesta.duckdb"

con = duckdb.connect(primary_db, read_only=True)

news_by_source = {}
try:
    rows = con.execute("SELECT source, count(*), min(published_at), max(published_at) FROM core.news GROUP BY source").fetchall()
    for s, c, mn, mx in rows:
        news_by_source[s] = {"count": c, "min_date": str(mn), "max_date": str(mx), "table": "core.news"}
except Exception as e:
    print(f"Error querying core.news: {e}")

macro_by_source = {}
try:
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core'").fetchall()]
    if "macro_policy" in tables:
        rows = con.execute("SELECT source, count(*), min(published_at), max(published_at) FROM core.macro_policy GROUP BY source").fetchall()
        for s, c, mn, mx in rows:
            macro_by_source[s] = {"count": c, "min_date": str(mn), "max_date": str(mx), "table": "core.macro_policy"}
except Exception as e:
    print(f"Error querying core.macro_policy: {e}")

con.close()

# Also check db/vesta.duckdb for any differences
if os.path.exists("db/vesta.duckdb") and primary_db != "db/vesta.duckdb":
    con2 = duckdb.connect("db/vesta.duckdb", read_only=True)
    try:
        t2 = [r[0] for r in con2.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core'").fetchall()]
        print(f"Tables in db/vesta.duckdb: {t2}")
        if "news" in t2:
            print("vesta.duckdb news:", con2.execute("SELECT source, count(*) FROM core.news GROUP BY source").fetchall())
        if "macro_policy" in t2:
            print("vesta.duckdb macro_policy:", con2.execute("SELECT source, count(*) FROM core.macro_policy GROUP BY source").fetchall())
    except Exception as e:
        print(f"Error checking vesta.duckdb: {e}")
    con2.close()

# 2. Load configurations from robots_global.yaml
with open("configs/robots_global.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

# Tier 1 & 2
configured_sites = {}
configured_sites["vnstock"] = {
    "name": "vnstock / vnstock_data (Community API)",
    "tier": "Tier 1",
    "category": "Corporate Equities",
    "target_table": "core.news",
    "status": "ACTIVE"
}
configured_sites["cafef"] = {
    "name": "CafeF Financial Portal",
    "tier": "Tier 2",
    "category": "Corporate & Financial News",
    "target_table": "core.news",
    "status": "ACTIVE"
}
configured_sites["vietstock"] = {
    "name": "Vietstock Finance Portal",
    "tier": "Tier 2",
    "category": "Market & Research Reports",
    "target_table": "core.macro_policy / stock_research_reports",
    "status": "ACTIVE"
}

# Tier 3 sources
for group_key, group_data in cfg.get("tier3_sources", {}).items():
    cat_name = group_key.replace("_", " ").title()
    for src_key, src_val in group_data.items():
        name = src_val.get("name", src_key)
        url = src_val.get("base_url") or src_val.get("url") or ""
        status = src_val.get("status", "ACTIVE")
        configured_sites[src_key] = {
            "name": name,
            "tier": "Tier 3",
            "category": cat_name,
            "url": url,
            "status": status,
            "target_table": "core.macro_policy"
        }

# Also inspect all robots files in scratch/exploration/robots
robots_dir = "scratch/exploration/robots"
robot_stems = set()
if os.path.exists(robots_dir):
    for f in os.listdir(robots_dir):
        if f.endswith(".txt") and f != "test_symbols.txt":
            stem = f.replace("-robots.txt", "").replace("_vn", "").replace(".txt", "")
            robot_stems.add(stem)

# 3. Match crawled vs uncrawled
all_crawled = {}
for s, data in news_by_source.items():
    all_crawled[s] = data
for s, data in macro_by_source.items():
    if s in all_crawled:
        all_crawled[s]["macro_count"] = data["count"]
    else:
        all_crawled[s] = data

# Print full breakdown
print("\n" + "="*100)
print(f"1. ALL CRAWLED NEWS SOURCES IN DATABASE ({len(all_crawled)} sources)")
print("="*100)
print(f"{'Source Key':<22} | {'Table':<18} | {'Articles':<10} | {'Date Range':<25}")
print("-" * 100)

total_articles = 0
for s, info in sorted(all_crawled.items(), key=lambda x: -x[1]["count"]):
    cnt = info["count"]
    total_articles += cnt
    dates = f"{info.get('min_date', '')[:10]} to {info.get('max_date', '')[:10]}"
    tbl = info["table"]
    print(f"{s:<22} | {tbl:<18} | {cnt:<10,} | {dates:<25}")

print("-" * 100)
print(f"TOTAL CRAWLED NEWS ARTICLES: {total_articles:,}")

# 4. Sites configured but NOT yet crawled or with 0 records
print("\n" + "="*100)
print("2. CONFIGURED / AUDITED SOURCES NOT YET CRAWLED (OR 0 ARTICLES)")
print("="*100)
not_crawled = []
for key, info in configured_sites.items():
    # Check aliases
    aliases = [
        key,
        key.replace("_gov_vn", ""),
        key.replace("_gov", ""),
        key.replace("_vn", ""),
        key.replace("_org_vn", ""),
        key.replace("_org", ""),
        key.replace("_com_vn", ""),
        key.replace("_com", ""),
        "worldbank" if "worldbank" in key else key,
        "luatvietnam" if "luat" in key else key,
    ]
    found = any(a in all_crawled for a in aliases)
    if not found:
        not_crawled.append((key, info))

print(f"{'Source Key':<25} | {'Name / Domain':<32} | {'Tier / Category':<25} | {'Status'}")
print("-" * 100)
for key, info in sorted(not_crawled, key=lambda x: x[1].get("status", "")):
    name = info["name"][:30]
    cat = f"{info['tier']} - {info['category']}"[:24]
    st = info.get("status", "PENDING")
    print(f"{key:<25} | {name:<32} | {cat:<25} | {st}")

print("-" * 100)
print(f"TOTAL NOT YET CRAWLED SOURCES: {len(not_crawled)}")
