import duckdb
import os
import sys

con = duckdb.connect("d:/VESTA/db/vesta_ohlcv.duckdb", read_only=True)
con.execute("ATTACH 'd:/VESTA/db/vesta_news.duckdb' AS news_db (READ_ONLY)")
con.execute("ATTACH 'd:/VESTA/db/vesta_snapshot.duckdb' AS snapshot (READ_ONLY)")

# 1. Query news from news_db
news_cnt = con.execute("SELECT count(*) FROM news_db.core.news").fetchone()[0]
print("news_db.core.news count:", news_cnt)

# 2. Query corporate events from snapshot
ev_cnt = con.execute("SELECT count(*) FROM snapshot.core.corporate_events").fetchone()[0]
print("snapshot.core.corporate_events count:", ev_cnt)

# 3. Check sample event
sample_ev = con.execute("SELECT symbol, event_type, event_date, detail_json FROM snapshot.core.corporate_events LIMIT 2").fetchall()
print("Sample event:", sample_ev[0][0], sample_ev[0][1], sample_ev[0][2])
import json
try:
    d = json.loads(sample_ev[0][3])
    print("Event detail keys:", list(d.keys()))
    print("Event detail sample:", {k: d[k] for k in list(d.keys())[:5]})
except Exception as e:
    print("Error parsing detail_json:", e)

con.close()
