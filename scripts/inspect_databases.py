import glob
import duckdb

print("=== CHECKING ALL DUCKDB FILES ===")
for p in glob.glob("db/*.duckdb"):
    try:
        con = duckdb.connect(p, read_only=True)
        tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')").fetchall()
        print(f"\nDB FILE: {p}")
        for s, t in tables:
            lower = t.lower()
            if any(k in lower for k in ['news', 'event', 'ohlcv', 'disclos', 'report', 'sentiment', 'shareholder', 'fundament', 'ratio']):
                cnt = con.execute(f'SELECT COUNT(*) FROM "{s}"."{t}"').fetchone()[0]
                cols = [c[0] for c in con.execute(f'PRAGMA table_info("{s}"."{t}")').fetchall()]
                print(f"  {s}.{t} ({cnt} rows)")
                print(f"     cols: {cols}")
                if cnt > 0 and any(k in lower for k in ['news', 'event', 'disclos', 'report']):
                    sample = con.execute(f'SELECT * FROM "{s}"."{t}" LIMIT 2').fetchall()
                    print(f"     sample 0: {sample[0] if sample else None}")
        con.close()
    except Exception as e:
        print(f"Error reading {p}: {e}")
