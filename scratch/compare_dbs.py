import duckdb
import os

for name in ['vesta_snapshot.duckdb', 'vesta.duckdb', 'vesta_crawled_fresh.duckdb']:
    path = f'db/{name}'
    if not os.path.exists(path):
        print(f"=== {name} (NOT FOUND) ===")
        continue
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"\n=== {name} ({size_mb:.2f} MB) ===")
    try:
        con = duckdb.connect(path, read_only=True)
        tables = con.execute("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_schema IN ('core', 'staging', 'meta') 
            ORDER BY 1, 2
        """).fetchall()
        for s, t in tables:
            try:
                cnt = con.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
                print(f"  {s}.{t}: {cnt:,} rows")
            except Exception as e:
                print(f"  {s}.{t}: ERROR {e}")
        con.close()
    except Exception as e:
        print(f"  FAILED to connect: {e}")
