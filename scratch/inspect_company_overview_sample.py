import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb

con = duckdb.connect('db/vesta_backup.duckdb', read_only=True)
sample = con.execute("""
    SELECT symbol, ceo_name, ceo_position, inspector_name, inspector_position, company_type, exchange
    FROM core.company_overview
    WHERE ceo_name IS NOT NULL AND length(ceo_name) > 3
    LIMIT 10
""").df()
print(sample.to_string())
con.close()
