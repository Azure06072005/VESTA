import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb

con = duckdb.connect('db/vesta_backup.duckdb', read_only=True)
cols = con.execute("DESCRIBE core.company_overview").df()
print("All columns of core.company_overview:")
for idx, row in cols.iterrows():
    print(f"  {row['column_name']} ({row['column_type']})")

sample = con.execute("SELECT symbol, icb_name, company_profile, history_dev, company_promise, business_risk, key_executives FROM core.company_overview LIMIT 1").df()
print("\nSample company_overview:")
print(sample.to_dict(orient='records')[0])
con.close()
