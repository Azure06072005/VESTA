import duckdb
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)
row = con.execute("SELECT * FROM core.news WHERE source='cafef' ORDER BY random() LIMIT 1").fetchone()
columns = [desc[0] for desc in con.description]
print(json.dumps(dict(zip(columns, row)), indent=2, default=str))
