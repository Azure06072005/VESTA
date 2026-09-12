import duckdb
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_latest_backup.duckdb", read_only=True)

print("--- BAODAUTU SAMPLES ---")
for url, body in con.execute("SELECT source_url, body FROM core.macro_policy WHERE source='baodautu' LIMIT 5").fetchall():
    date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", body[:300])
    date_found = date_match.group(1) if date_match else "None"
    print(f"URL: {url}")
    print(f"Detected Date: {date_found} | Body preview: {body[:100]}...\n")

print("--- THOIBAONGANHANG SAMPLES ---")
for url, body in con.execute("SELECT source_url, body FROM core.macro_policy WHERE source='thoibaonganhang' LIMIT 5").fetchall():
    date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", body[:300])
    date_found = date_match.group(1) if date_match else "None"
    print(f"URL: {url}")
    print(f"Detected Date: {date_found} | Body preview: {body[:100]}...\n")

con.close()
