import os
import sys

REPO_ROOT = r"d:\VESTA"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if os.path.join(REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from src.service.console_api import get_lakehouse_status

res = get_lakehouse_status()
tables = res.get("tables", [])
print(f"Total tables tracked: {len(tables)}")
for item in tables:
    name = item["name"]
    tbl = item["table"]
    recs = item["records"]
    mdate = item["max_date"]
    st = item["status"]
    print(f"{name:<42} : {tbl:<36} : {recs:>10} rows : max={mdate} ({st})")
