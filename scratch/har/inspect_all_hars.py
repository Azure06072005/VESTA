import json
import os
from pathlib import Path
from bs4 import BeautifulSoup
import duckdb

har_base = Path("scratch/har")

# Check existing URLs in backup and crawlers_staging
seen_urls = set()
for db_path in ["db/crawlers_staging.duckdb", "db/vesta_latest_backup.duckdb"]:
    if os.path.exists(db_path):
        try:
            con = duckdb.connect(db_path, read_only=True)
            for row in con.execute("SELECT source_url FROM core.macro_policy").fetchall():
                seen_urls.add(row[0])
            con.close()
        except Exception as e:
            print(f"Error reading {db_path}: {e}")

print(f"Total existing unique macro_policy URLs in databases: {len(seen_urls):,}")

for folder in sorted(har_base.iterdir()):
    if not folder.is_dir():
        continue
    har_files = list(folder.glob("*.har"))
    print(f"\n=======================================================")
    print(f"FOLDER: {folder.name} ({len(har_files)} .har files)")
    print(f"=======================================================")
    
    total_entries = 0
    total_articles_detected = 0
    sample_urls = []
    
    for hf in sorted(har_files):
        try:
            with open(hf, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            entries = data.get("log", {}).get("entries", [])
            total_entries += len(entries)
            
            # Count useful HTML and JSON responses
            html_count = 0
            json_count = 0
            for e in entries:
                mime = e.get("response", {}).get("content", {}).get("mimeType", "")
                text = e.get("response", {}).get("content", {}).get("text", "")
                url = e.get("request", {}).get("url", "")
                if "html" in mime and len(text) > 1000:
                    html_count += 1
                elif "json" in mime and len(text) > 500:
                    json_count += 1
            print(f"  - {hf.name:<35} | Entries: {len(entries):<5} | HTML: {html_count:<3} | JSON: {json_count:<3}")
        except Exception as e:
            print(f"  - {hf.name:<35} | ERROR reading: {e}")
