"""test_pipeline/scripts/extract_sample_records.py

Extracts real representative sample records from db/test_db/vesta_test.duckdb
demonstrating the 4 temporal alignment phenomena.
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DB_PATH = "db/test_db/vesta_test.duckdb"

def extract_samples():
    con = duckdb.connect(DB_PATH, read_only=True)
    
    print("### SAMPLE 1: MIDNIGHT 00:00:00 TIMESTAMPS (LOOK-AHEAD HAZARD)")
    q1 = """
    SELECT 
        p.symbol,
        p.published_at,
        p.headline,
        p.price_at_publish as price_t0_close,
        p.price_t1 as price_t1_close,
        ROUND((p.price_t1 - p.price_at_publish) / p.price_at_publish * 100, 2) as ret_t0_to_t1_pct
    FROM core.pit_events p
    WHERE date_part('hour', p.published_at) = 0 
      AND date_part('minute', p.published_at) = 0 
      AND date_part('second', p.published_at) = 0
      AND p.price_at_publish > 0 AND p.price_t1 > 0
    LIMIT 4
    """
    df1 = con.execute(q1).df()
    print(df1.to_string(index=False))
    
    print("\n### SAMPLE 2: POINT-IN-TIME FUNDAMENTALS (CIRCULAR 96 STATUTORY LAG)")
    q2 = """
    SELECT 
        p.symbol,
        p.published_at::DATE as event_date,
        f.period_end as bctc_quarter_end,
        f.available_at as statutory_available_at,
        date_diff('day', f.period_end, f.available_at) as disclosure_lag_days,
        date_diff('day', f.available_at, p.published_at::DATE) as days_since_disclosed,
        json_extract_string(f.data_json, '$.roe') as roe,
        json_extract_string(f.data_json, '$.pe') as pe
    FROM core.pit_events p
    JOIN core.fundamentals f 
      ON p.symbol = f.symbol 
     AND p.published_at::DATE >= f.available_at
    WHERE f.data_json IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (PARTITION BY p.symbol ORDER BY f.period_end DESC) = 1
    LIMIT 4
    """
    df2 = con.execute(q2).df()
    print(df2.to_string(index=False))
    
    print("\n### SAMPLE 3: FROZEN / SUSPENDED STOCKS (FLATLINE ROLLOVER P0=P1=P5=P30)")
    q3 = """
    SELECT 
        symbol,
        published_at::DATE as event_date,
        headline,
        price_at_publish as p_t0,
        price_t1 as p_t1,
        price_t5 as p_t5,
        price_t30 as p_t30
    FROM core.pit_events
    WHERE price_at_publish > 0
      AND price_t1 = price_at_publish
      AND price_t5 = price_at_publish
      AND price_t30 = price_at_publish
    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY published_at) = 1
    LIMIT 4
    """
    df3 = con.execute(q3).df()
    print(df3.to_string(index=False))

    print("\n### SAMPLE 4: RAW ZERO-PRICE DATA DEFECTS (DIV-BY-ZERO HAZARD)")
    q4 = """
    SELECT 
        symbol,
        published_at,
        headline,
        price_at_publish,
        price_t1,
        price_t5
    FROM core.pit_events
    WHERE price_at_publish <= 0
    LIMIT 4
    """
    df4 = con.execute(q4).df()
    print(df4.to_string(index=False))
    
    con.close()

if __name__ == "__main__":
    extract_samples()
