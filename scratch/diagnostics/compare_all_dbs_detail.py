import duckdb
import os

db_list = [
    ("Main DB", "db/vesta.duckdb"),
    ("Backup DB", "db/vesta_latest_backup.duckdb"),
    ("Consolidated Snapshot", "db/vesta_consolidated.duckdb"),
    ("Staging DB", "db/crawlers_staging.duckdb")
]

results = {}

for name, path in db_list:
    if not os.path.exists(path):
        continue
    size_mb = os.path.getsize(path) / (1024 * 1024)
    con = duckdb.connect(path, read_only=True)
    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('core', 'staging', 'main') ORDER BY table_schema, table_name").fetchall()
    table_info = {}
    for s, t in tables:
        full_t = f"{s}.{t}"
        count = con.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
        cols = con.execute(f"SELECT count(*) FROM information_schema.columns WHERE table_schema = '{s}' AND table_name = '{t}'").fetchone()[0]
        table_info[full_t] = {"rows": count, "cols": cols}
    
    # Check extra metrics on macro_policy if exists
    macro_metrics = {}
    if "core.macro_policy" in table_info:
        res = con.execute("SELECT count(*), count(distinct source), min(published_at), max(published_at), avg(length(body)) FROM core.macro_policy").fetchone()
        macro_metrics = {
            "total_articles": res[0],
            "distinct_sources": res[1],
            "earliest_date": str(res[2]),
            "latest_date": str(res[3]),
            "avg_body_len": round(res[4] or 0, 1)
        }
    
    results[name] = {
        "path": path,
        "size_mb": round(size_mb, 1),
        "table_count": len(table_info),
        "tables": table_info,
        "macro_metrics": macro_metrics
    }
    con.close()

import json
print(json.dumps(results, indent=2))
