import sys
sys.stdout.reconfigure(encoding="utf-8")
import duckdb
import pandas as pd

con = duckdb.connect("db/test_db/vesta_test.duckdb", read_only=True)

df_ind = con.execute("""
    SELECT industry_name, industry_code, count(*) as n_symbols
    FROM core.dim_symbol
    GROUP BY 1, 2
    ORDER BY 3 DESC
""").df()
print("\n--- Industry distribution in core.dim_symbol ---")
print(df_ind.to_string())

# Also check canonical db to see if core.dim_sector / core.dim_symbol_sector exist in db/vesta.duckdb
con_canon = duckdb.connect("db/vesta.duckdb", read_only=True)
canon_tables = [t[0] for t in con_canon.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'core'").fetchall()]
print("\n--- Core tables in db/vesta.duckdb ---")
print(canon_tables)

if "dim_sector" in canon_tables:
    print("\n--- core.dim_sector in db/vesta.duckdb ---")
    print(con_canon.execute("SELECT * FROM core.dim_sector").df().to_string())

con.close()
con_canon.close()
