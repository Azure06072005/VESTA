import pandas as pd
import duckdb

con = duckdb.connect("db/vesta.duckdb", read_only=True)
df_val = con.execute("SELECT * FROM 'data/processed/f104/f104_val.parquet' LIMIT 5").df()
print("f104_val columns:", df_val.columns.tolist())
val_count = con.execute("SELECT count(*) FROM 'data/processed/f104/f104_val.parquet'").fetchone()[0]
test_count = con.execute("SELECT count(*) FROM 'data/processed/f104/f104_test.parquet'").fetchone()[0]
train_count = con.execute("SELECT count(*) FROM 'data/processed/f104/f104_train.parquet'").fetchone()[0]
print(f"Row counts: train={train_count:,}, val={val_count:,}, test={test_count:,}")

con = duckdb.connect("db/vesta.duckdb", read_only=True)
print("core.pit_events count:", con.execute("SELECT count(*) FROM core.pit_events").fetchone()[0])
print("core.pit_events cols:", [c[1] for c in con.execute("PRAGMA table_info('core.pit_events')").fetchall()])
con.close()
