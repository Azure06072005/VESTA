import duckdb
con = duckdb.connect('db/vesta.duckdb', read_only=True)
print("BBC in dim_symbol:")
print(con.execute("SELECT * FROM core.dim_symbol WHERE symbol='BBC'").fetchall())

print("\nSample of missing symbols (checking 5 non-bonds):")
df = con.execute("SELECT symbol FROM core.dim_symbol").fetchdf()
vnstock_symbols = set(df['symbol'])

import json
with open('scratch/cafef_company_list.json', encoding='utf-8') as f:
    cafef = json.load(f)

missing = []
for c in cafef:
    sym = c['Symbol']
    center = c['CenterId']
    if center in [1, 2, 9] and sym not in vnstock_symbols:
        org_name = c['Title']
        if "Trái phiếu" not in org_name and "Trái Phiếu" not in org_name and "Chứng quyền" not in org_name:
            missing.append((sym, org_name))

print(f"Total non-bond non-warrant missing equities from HOSE/HNX/UPCOM: {len(missing)}")
for m in missing[:10]:
    print(m)
