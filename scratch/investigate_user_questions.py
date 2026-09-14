"""scratch/investigate_user_questions.py

Investigates:
1. Storage decomposition of db/vesta.duckdb (7.84GB) vs vesta_preprocessed_full.duckdb (222MB).
2. Filtered events breakdown by source (invalid prices, flatlines).
3. Find all tables with data_json or JSON columns and inspect their schemas.
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta.duckdb", read_only=True)

print("=" * 85)
print("INVESTIGATION 1: WHERE IS data_json?")
print("=" * 85)
cols = con.execute("""
    SELECT table_schema, table_name, column_name, data_type 
    FROM information_schema.columns 
    WHERE column_name LIKE '%json%' 
       OR column_name LIKE '%data%'
       OR data_type LIKE '%JSON%'
    ORDER BY table_schema, table_name
""").df()
print(cols.to_string(index=False))

# Check table samples where data_json exists
for _, r in cols.iterrows():
    schema, tbl, col = r['table_schema'], r['table_name'], r['column_name']
    try:
        sample = con.execute(f"SELECT {col} FROM {schema}.{tbl} WHERE {col} IS NOT NULL LIMIT 1").fetchone()
        if sample:
            print(f"\nSample from {schema}.{tbl}.{col} (first 250 chars):")
            print(str(sample[0])[:250])
    except Exception as e:
        pass

print("\n" + "=" * 85)
print("INVESTIGATION 2: WHY IS vesta_preprocessed_full.duckdb 222MB vs vesta.duckdb 7.84GB?")
print("=" * 85)
print("Raw table sizes and row counts in vesta.duckdb:")
tables = con.execute("""
    SELECT table_schema, table_name 
    FROM information_schema.tables 
    WHERE table_schema IN ('core', 'staging')
    ORDER BY table_schema, table_name
""").df()

for _, r in tables.iterrows():
    schema, tname = r['table_schema'], r['table_name']
    cnt = con.execute(f"SELECT count(*) FROM {schema}.{tname}").fetchone()[0]
    print(f" - {schema}.{tname:<32} : {cnt:>12,} rows")

print("\n" + "=" * 85)
print("INVESTIGATION 3: SOURCES OF FILTERED/REMOVED EVENTS (658,182 -> 581,944)")
print("=" * 85)
# Audit removal breakdown by source
q_filtered = """
SELECT 
    CASE 
        WHEN source_url LIKE '%cafef.vn%' THEN 'cafef'
        WHEN source_url LIKE '%tinnhanhchungkhoan.vn%' THEN 'tinnhanhchungkhoan'
        WHEN source_url LIKE '%vietstock.vn%' THEN 'vietstock'
        ELSE 'other_sources'
    END as news_source,
    count(*) as total_events,
    sum(CASE WHEN price_at_publish <= 0 OR price_t5 <= 0 OR price_t30 <= 0 OR price_at_publish IS NULL OR price_t5 IS NULL OR price_t30 IS NULL THEN 1 ELSE 0 END) as invalid_price_count,
    sum(CASE WHEN price_at_publish > 0 AND price_t5 > 0 AND price_t30 > 0 AND (price_at_publish = price_t5 AND price_t5 = price_t30) THEN 1 ELSE 0 END) as flatline_count,
    sum(CASE WHEN price_at_publish > 0 AND price_t5 > 0 AND price_t30 > 0 AND NOT (price_at_publish = price_t5 AND price_t5 = price_t30) THEN 1 ELSE 0 END) as retained_count
FROM core.pit_events
GROUP BY 1
ORDER BY total_events DESC
"""
df_filt = con.execute(q_filtered).df()
df_filt["removal_rate_pct"] = round((df_filt["invalid_price_count"] + df_filt["flatline_count"]) / df_filt["total_events"] * 100, 2)
print(df_filt.to_string(index=False))

# Check by exchange as well
print("\nRemoval breakdown by Exchange:")
q_exch = """
SELECT 
    COALESCE(s.exchange, 'UNKNOWN / DELISTED') as exchange,
    count(*) as total_events,
    sum(CASE WHEN p.price_at_publish <= 0 OR p.price_t5 <= 0 OR p.price_t30 <= 0 OR p.price_at_publish IS NULL OR p.price_t5 IS NULL OR p.price_t30 IS NULL THEN 1 ELSE 0 END) as invalid_price_count,
    sum(CASE WHEN p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0 AND (p.price_at_publish = p.price_t5 AND p.price_t5 = p.price_t30) THEN 1 ELSE 0 END) as flatline_count,
    sum(CASE WHEN p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0 AND NOT (p.price_at_publish = p.price_t5 AND p.price_t5 = p.price_t30) THEN 1 ELSE 0 END) as retained_count
FROM core.pit_events p
LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
GROUP BY COALESCE(s.exchange, 'UNKNOWN / DELISTED')
ORDER BY total_events DESC
"""
df_exch = con.execute(q_exch).df()
df_exch["removal_rate_pct"] = round((df_exch["invalid_price_count"] + df_exch["flatline_count"]) / df_exch["total_events"] * 100, 2)
print(df_exch.to_string(index=False))

con.close()
