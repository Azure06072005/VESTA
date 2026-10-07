import duckdb
import os
import json

db_path = "d:/VESTA/db/vesta_snapshot.duckdb"
config = {"access_mode": "read_only", "threads": "2"}
try:
    con = duckdb.connect(db_path, read_only=True, config=config)
    cnt = con.execute("SELECT count(*) FROM core.corporate_events").fetchone()[0]
    print("Corporate events count in snapshot:", cnt)
    
    rows = con.execute("SELECT symbol, event_type, event_date, detail_json FROM core.corporate_events LIMIT 5").fetchall()
    for r in rows:
        d = json.loads(r[3])
        title = d.get("event_title") or d.get("event_name") or d.get("content") or d.get("event_desc") or r[1]
        print(f"[{r[0]}] {r[1]} | date: {r[2]} | title: {title[:40]}")
    con.close()
    print("SUCCESS reading corporate_events!")
except Exception as e:
    print("Error:", e)
