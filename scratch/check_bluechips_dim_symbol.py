import duckdb
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
symbols = ['FPT', 'VIC', 'HPG', 'VNM', 'MSN', 'MWG', 'VCB', 'TCB', 'MBB', 'STB', 'SSI', 'VND', 'VHM', 'VRE']
df = con.execute(f"SELECT symbol, organ_name, en_organ_name FROM core.dim_symbol WHERE symbol IN ({','.join(repr(s) for s in symbols)})").df()
con.close()

print(df.to_string(index=False))
