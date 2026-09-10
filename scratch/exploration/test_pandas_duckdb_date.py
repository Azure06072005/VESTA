import duckdb
import datetime as dt
import pandas as pd

con = duckdb.connect(":memory:")
con.execute("CREATE TABLE t (ex_date DATE, mult DOUBLE)")
con.execute("INSERT INTO t VALUES ('2026-05-28', 0.9)")
df = con.execute("SELECT * FROM t").df()
print("ex_date dtype in pandas:", df["ex_date"].dtype)

try:
    sub = df[df["ex_date"] > dt.date(2026, 1, 1)]
    print("Direct comparison with dt.date succeeded")
except Exception as e:
    print("Direct comparison with dt.date FAILED:", type(e), e)

try:
    sub2 = df[pd.to_datetime(df["ex_date"]).dt.date > dt.date(2026, 1, 1)]
    print("Comparison via .dt.date succeeded! Result count:", len(sub2))
except Exception as e:
    print("Comparison via .dt.date FAILED:", type(e), e)
