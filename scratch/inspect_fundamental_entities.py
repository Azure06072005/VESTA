import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb
import pandas as pd

con = duckdb.connect('db/vesta_backup.duckdb', read_only=True)

for table_name in ['company_shareholders', 'company_overview', 'dim_symbol_cafef', 'dim_symbol']:
    print(f"\n================ TABLE: core.{table_name} ================")
    cols = con.execute(f"DESCRIBE core.{table_name}").df()
    print("Columns:")
    print(cols[['column_name', 'column_type']].to_string(index=False))
    sample = con.execute(f"SELECT * FROM core.{table_name} LIMIT 3").df()
    print("\nSample Rows:")
    print(sample.to_string())

con.close()
