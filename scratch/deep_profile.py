import duckdb
import pandas as pd
import json

con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)

# 1. Year by year distribution for OHLCV daily
print("=== OHLCV DAILY BY YEAR ===")
ohlcv_by_year = con.execute("""
    SELECT EXTRACT(year FROM date) as yr, count(*) as cnt, count(distinct symbol) as sym_cnt
    FROM core.market_ohlcv_daily
    GROUP BY yr
    ORDER BY yr
""").df()
print(ohlcv_by_year.to_string())

# 2. Year by year distribution for News
print("\n=== NEWS BY YEAR ===")
news_by_year = con.execute("""
    SELECT EXTRACT(year FROM published_at) as yr, count(*) as cnt, count(distinct symbol) as sym_cnt
    FROM core.news
    GROUP BY yr
    ORDER BY yr
""").df()
print(news_by_year.to_string())

# 3. Year by year distribution for Foreign Flow
print("\n=== FOREIGN FLOW BY YEAR ===")
foreign_by_year = con.execute("""
    SELECT EXTRACT(year FROM date) as yr, count(*) as cnt, count(distinct symbol) as sym_cnt
    FROM core.market_foreign_flow_daily
    GROUP BY yr
    ORDER BY yr
""").df()
print(foreign_by_year.to_string())

# 4. Fundamentals structure
print("\n=== FUNDAMENTALS INFO ===")
fund_types = con.execute("""
    SELECT type, count(*) as cnt, count(distinct symbol) as sym_cnt
    FROM core.fundamentals
    GROUP BY type
""").df()
print(fund_types.to_string())

# 5. Financial notes structure
print("\n=== FINANCIAL NOTES INFO ===")
notes_cols = con.execute("DESCRIBE core.financial_notes").df()
print(notes_cols[['column_name', 'column_type']].to_string())
sample_notes = con.execute("SELECT * FROM core.financial_notes LIMIT 3").df()
print(sample_notes.to_string())

# 6. Corporate events breakdown
print("\n=== CORPORATE EVENTS BY TYPE ===")
events_types = con.execute("""
    SELECT event_type, count(*) as cnt, min(event_date) as min_d, max(event_date) as max_d
    FROM core.corporate_events
    GROUP BY event_type
""").df()
print(events_types.to_string())

# 7. Check 1204 date anomaly in preprocessed.macro_policy and news_resources
print("\n=== DATE ANOMALIES IN MACRO_POLICY ===")
policy_anom = con.execute("""
    SELECT source, title, published_at 
    FROM preprocessed.macro_policy 
    WHERE published_at < '1990-01-01' OR published_at > '2026-12-31'
    LIMIT 10
""").df()
print(policy_anom.to_string())

# 8. Indexes in market_index_daily
print("\n=== INDICES IN MARKET_INDEX_DAILY ===")
indices = con.execute("""
    SELECT index_code, count(*) as cnt, min(date) as min_d, max(date) as max_d
    FROM core.market_index_daily
    GROUP BY index_code
    ORDER BY cnt DESC
""").df()
print(indices.to_string())

# 9. Proprietary flow by year
print("\n=== PROPRIETARY FLOW BY YEAR ===")
prop_by_year = con.execute("""
    SELECT EXTRACT(year FROM date) as yr, count(*) as cnt, count(distinct symbol) as sym_cnt
    FROM core.proprietary_flow
    GROUP BY yr
    ORDER BY yr
""").df()
print(prop_by_year.to_string())

con.close()
