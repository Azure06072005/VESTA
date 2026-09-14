"""scratch/inspect_preprocessed.py

Inspects existing parquet files in test_pipeline/out/
"""
import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect()
try:
    df = con.execute("SELECT * FROM read_parquet('test_pipeline/out/test_features_matrix.parquet') LIMIT 5").df()
    print("=== TEST FEATURES MATRIX PARQUET ===")
    print("Columns:", list(df.columns))
    print(df.head(3))
except Exception as e:
    print("Error reading parquet:", e)
finally:
    con.close()
