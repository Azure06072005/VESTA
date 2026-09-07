import os
import duckdb

robots_dir = "d:/VESTA/scratch/robots"
files = sorted([f for f in os.listdir(robots_dir) if f.endswith(".txt") and f != "test_symbols.txt"])

con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)
policy_sources = set(r[0] for r in con.execute("SELECT DISTINCT source FROM core.macro_policy").fetchall())
news_sources = set(r[0] for r in con.execute("SELECT DISTINCT source FROM core.news").fetchall())
con.close()

crawlers = set(os.listdir("d:/VESTA/src/crawlers"))
done_sources = policy_sources | news_sources | {"vietstock_finance", "cafef_bctc", "vnstock_data"}

site_status = {}
for f in files:
    stem = f.replace("-robots.txt", "")
    crawler_found = None
    db_found = None

    candidates = [
        stem,
        stem.replace("_vn", "").replace("_com", "").replace("_org", "").replace("_gov", ""),
        stem.split("_")[0],
    ]

    for c in crawlers:
        for cand in candidates:
            if cand in c and ("crawler" in c or "enhancer" in c or "news" in c or "foreign" in c):
                crawler_found = c
                break
        if crawler_found:
            break

    for s in done_sources:
        for cand in candidates:
            if cand == s or cand in s or s in cand:
                db_found = s
                break
        if db_found:
            break

    status = "PENDING"
    if "wsj" in stem:
        status = "BLOCKED_RFC9309"
    elif db_found or crawler_found:
        status = "DONE"

    site_status[f] = {
        "stem": stem,
        "crawler": crawler_found,
        "db_source": db_found,
        "status": status,
    }

done_count = sum(1 for v in site_status.values() if v["status"] == "DONE")
pending_count = sum(1 for v in site_status.values() if v["status"] == "PENDING")
blocked_count = sum(1 for v in site_status.values() if v["status"] == "BLOCKED_RFC9309")

print(f"SUMMARY: DONE={done_count}, PENDING={pending_count}, BLOCKED={blocked_count}")
print("=" * 95)
for f, info in sorted(site_status.items()):
    st = info["status"]
    cr = str(info["crawler"]) if info["crawler"] else "-"
    db_s = str(info["db_source"]) if info["db_source"] else "-"
    print(f"{st:15s} | {f:32s} | crawler: {cr:30s} | db: {db_s}")
