"""scratch/test_json_extraction.py

Tests DuckDB native json extraction on core.fundamentals.data_json
"""
import sys
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

q = """
SELECT 
    symbol,
    period_end,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_PE') AS FLOAT) as pe_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_PB') AS FLOAT) as pb_ratio,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_ROE') AS FLOAT) as roe,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_ROA') AS FLOAT) as roa,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_EV_EBITDA') AS FLOAT) as ev_ebitda,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_DIVIDEND_YIELD') AS FLOAT) as dividend_yield,
    TRY_CAST(json_extract(data_json, '$.RT_VALUE_MARKET_CAP') AS FLOAT) as market_cap_billions
FROM core.fundamentals 
WHERE data_json IS NOT NULL 
  AND TRY_CAST(json_extract(data_json, '$.RT_VALUE_PE') AS FLOAT) > 0
ORDER BY period_end DESC
LIMIT 6
"""
df = con.execute(q).df()
print("=== DEMO: SELECTIVE JSON FLATTENING IN DUCKDB ===")
print(df.to_string(index=False))

con.close()
