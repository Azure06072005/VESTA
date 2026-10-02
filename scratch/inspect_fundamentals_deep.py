import json
import sys
import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_backup.duckdb", read_only=True)

print("=== 1. CORE.FUNDAMENTALS BREAKDOWN ===")
res_fun = con.execute("""
    SELECT 
        report_type,
        count(*) as total_rows,
        count(DISTINCT symbol) as distinct_symbols,
        min(period_end) as min_period_end,
        max(period_end) as max_period_end
    FROM core.fundamentals
    GROUP BY report_type
    ORDER BY total_rows DESC
""").df()
print(res_fun.to_string())

print("\n=== 2. FINANCIAL HEALTH SAMPLE (F-SCORE & Z-SCORE) ===")
sample_health = con.execute("""
    SELECT symbol, period_end, data_json
    FROM core.fundamentals
    WHERE report_type = 'financial_health'
    LIMIT 3
""").df()
for _, r in sample_health.iterrows():
    print(f"[{r['symbol']} - {r['period_end']}]: {r['data_json']}")

print("\n=== 3. CORPORATE EVENTS BREAKDOWN ===")
res_events = con.execute("""
    SELECT 
        coalesce(event_type, 'Khác') as event_type,
        count(*) as total_events,
        count(DISTINCT symbol) as distinct_symbols,
        min(event_date) as min_date,
        max(event_date) as max_date,
        round(avg(payout_delay_days), 1) as avg_payout_delay
    FROM core.corporate_events
    GROUP BY event_type
    ORDER BY total_events DESC
""").df()
print(res_events.to_string())

print("\n=== 4. MARKET SCREENER SNAPSHOT METRICS ===")
sample_screener = con.execute("""
    SELECT symbol, pe, pb, roe, roa, market_cap, revenue_growth, profit_growth
    FROM core.market_screener_snapshot
    WHERE pe IS NOT NULL AND pe > 0 AND pe < 100
    LIMIT 5
""").df()
print(sample_screener.to_string())

print("\n=== 5. FOREIGN FLOW DAILY SUMMARY ===")
res_ff = con.execute("""
    SELECT 
        count(*) as total_flow_records,
        count(DISTINCT symbol) as distinct_symbols,
        min(date) as min_date,
        max(date) as max_date,
        round(sum(net_value) / 1e12, 2) as total_net_value_trillion_vnd
    FROM core.market_foreign_flow_daily
""").df()
print(res_ff.to_string())

print("\n=== 6. PROPRIETARY FLOW SUMMARY ===")
res_prop = con.execute("""
    SELECT 
        count(*) as total_prop_records,
        count(DISTINCT symbol) as distinct_symbols,
        min(date) as min_date,
        max(date) as max_date,
        round(sum(net_val) / 1e12, 2) as total_prop_net_trillion_vnd
    FROM core.proprietary_flow
""").df()
print(res_prop.to_string())

print("\n=== 7. FINANCIAL NOTES SUMMARY ===")
res_notes = con.execute("""
    SELECT 
        count(*) as total_note_records,
        count(DISTINCT symbol) as distinct_symbols,
        count(DISTINCT note_name) as distinct_notes,
        min(period) as min_period,
        max(period) as max_period
    FROM core.financial_notes
""").df()
print(res_notes.to_string())

con.close()
