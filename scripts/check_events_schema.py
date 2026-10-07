import duckdb
import json

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
row = con.execute("SELECT symbol, event_type, event_date, detail_json FROM core.corporate_events WHERE detail_json IS NOT NULL LIMIT 5").fetchall()
for r in row:
    print(f"Symbol: {r[0]}, Type: {r[1]}, Date: {r[2]}")
    try:
        data = json.loads(r[3])
        print("  Keys:", list(data.keys()))
        for k in ['event_name_vi', 'event_title_vi', 'event_name', 'title', 'content', 'ratio', 'value', 'cash_dividend_percentage', 'exright_date']:
            if k in data:
                print(f"    {k}: {data[k]}")
    except Exception as e:
        print("  Error parsing JSON:", e)
con.close()
