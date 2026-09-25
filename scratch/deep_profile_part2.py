import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)

# 7. Check date anomalies in preprocessed.macro_policy and news_resources
print("\n=== DATE ANOMALIES IN MACRO_POLICY ===")
policy_anom = con.execute("""
    SELECT source, headline_clean, published_at 
    FROM preprocessed.macro_policy 
    WHERE published_at < '1990-01-01' OR published_at > '2026-12-31'
    LIMIT 10
""").df()
print(policy_anom.to_string())

# Total count of policy records by year
print("\n=== MACRO POLICY BY YEAR ===")
policy_by_year = con.execute("""
    SELECT EXTRACT(year FROM published_at) as yr, count(*) as cnt
    FROM preprocessed.macro_policy
    WHERE published_at >= '1990-01-01' AND published_at <= '2026-12-31'
    GROUP BY yr
    ORDER BY yr
""").df()
print(policy_by_year.to_string())

# 8. Indexes in market_index_daily
print("\n=== TOP 15 INDICES IN MARKET_INDEX_DAILY ===")
indices = con.execute("""
    SELECT index_code, count(*) as cnt, min(date) as min_d, max(date) as max_d
    FROM core.market_index_daily
    GROUP BY index_code
    ORDER BY cnt DESC
    LIMIT 15
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

# 10. News Resources breakdown by source
print("\n=== NEWS RESOURCES BY SOURCE ===")
resources = con.execute("""
    SELECT source, count(*) as cnt, min(published_at) as min_d, max(published_at) as max_d
    FROM core.news_resources
    GROUP BY source
    ORDER BY cnt DESC
""").df()
print(resources.to_string())

# 11. Market OHLCV 1m info
print("\n=== MARKET OHLCV 1M BY YEAR & MONTH ===")
ohlcv_1m = con.execute("""
    SELECT EXTRACT(year FROM time) as yr, count(*) as cnt, count(distinct symbol) as sym_cnt,
           min(time) as min_t, max(time) as max_t
    FROM core.market_ohlcv_1m
    GROUP BY yr
    ORDER BY yr
""").df()
print(ohlcv_1m.to_string())

con.close()
