"""scratch/test_asof_join.py

Tests ASOF JOIN in DuckDB between preprocessed.events and preprocessed.fundamentals_ratios
"""
import sys
import time
import duckdb

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

t0 = time.time()
q = """
WITH ratios AS (
    SELECT 
        symbol,
        available_at,
        period_end,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_PE') AS FLOAT) as pe_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_PB') AS FLOAT) as pb_ratio,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_ROE') AS FLOAT) as roe,
        TRY_CAST(json_extract(data_json, '$.RT_PRT_ROA') AS FLOAT) as roa,
        TRY_CAST(json_extract(data_json, '$.RT_VALUE_MARKET_CAP') AS FLOAT) as market_cap
    FROM core.fundamentals 
    WHERE report_type = 'ratio' AND data_json IS NOT NULL
)
SELECT 
    e.symbol,
    e.event_date,
    e.headline_clean,
    r.period_end as bctc_period_end,
    r.available_at as bctc_available_at,
    r.pe_ratio,
    r.pb_ratio,
    r.roe
FROM preprocessed.events e
ASOF JOIN ratios r
  ON e.symbol = r.symbol AND e.event_date >= r.available_at
WHERE r.pe_ratio IS NOT NULL
ORDER BY e.event_date DESC
LIMIT 8
"""
df = con.execute(q).df()
t1 = time.time()

print("=== ASOF JOIN TEST RESULTS ===")
print(df.to_string(index=False))
print(f"Executed in {t1 - t0:.2f} seconds!")

con.close()
