import duckdb
import json

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
query = """
    SELECT symbol, snapshot_at, data_json 
    FROM core.realtime_quote_snapshot 
    WHERE snapshot_at >= '2026-09-27' 
      AND symbol IN ('FPT', 'VNM', 'HPG', 'VCB')
    ORDER BY symbol
"""
rows = con.execute(query).fetchall()
print(f"Found {len(rows)} matching rows on 2026-09-27:")
for sym, sat, d_json in rows:
    data = json.loads(d_json)
    print(f"\n=== Symbol: {sym} (Snapshot: {sat}) ===")
    print(f"  Total JSON Fields: {len(data)}")
    
    # Match info
    match_fields = {k: v for k, v in data.items() if 'match' in k}
    print("  Match Info:")
    for k in ['match_match_price', 'match_accumulated_volume', 'match_high_price', 'match_low_price', 'match_match_type']:
        if k in match_fields:
            print(f"    {k}: {match_fields[k]}")
            
    # Bid / Ask Level 2 depth
    ba_fields = {k: v for k, v in data.items() if 'bid_ask' in k}
    print("  Level 2 Order Book Depth:")
    for i in range(1, 4):
        bp = ba_fields.get(f'bid_ask_bid_{i}_price')
        bv = ba_fields.get(f'bid_ask_bid_{i}_volume')
        ap = ba_fields.get(f'bid_ask_ask_{i}_price')
        av = ba_fields.get(f'bid_ask_ask_{i}_volume')
        print(f"    [Level {i}] Bid: {bp:,} (Vol: {bv:,}) | Ask: {ap:,} (Vol: {av:,})" if bp and ap else f"    [Level {i}] Bid: {bp} | Ask: {ap}")

con.close()
