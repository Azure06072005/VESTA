import duckdb
import sys

print("Testing connect directly...")
try:
    con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
    print("Direct connect SUCCESS")
    con.close()
except Exception as e:
    print("Direct connect FAILED:", e)

print("\nTesting in-memory ATTACH READ_ONLY...")
try:
    mem = duckdb.connect()
    mem.execute("ATTACH 'd:/VESTA/db/vesta_snapshot.duckdb' AS snap (READ_ONLY);")
    print("Memory ATTACH SUCCESS:", mem.execute("SELECT count(*) FROM snap.core.fundamentals").fetchone())
    mem.close()
except Exception as e:
    print("Memory ATTACH FAILED:", e)
