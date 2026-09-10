import sys
import json
import pathlib
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

vnstock_db_path = pathlib.Path(r"d:\vnstock\db\production.duckdb")
vesta_db_path = pathlib.Path(r"d:\VESTA\db\vesta.duckdb")

con_vnstock = duckdb.connect(str(vnstock_db_path), read_only=True)
con_vesta = duckdb.connect(str(vesta_db_path), read_only=True)

# 1. Overall DB Tables comparison
print("="*80)
print("1. OVERALL DATABASE TABLES & ROW COUNTS COMPARISON")
print("="*80)

def get_tables(con):
    rows = con.execute("""
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name
    """).fetchall()
    counts = {}
    for s, t in rows:
        c = con.execute(f"SELECT COUNT(*) FROM {s}.{t}").fetchone()[0]
        counts[f"{s}.{t}"] = c
    return counts

vnstock_tables = get_tables(con_vnstock)
vesta_tables = get_tables(con_vesta)

print(f"\n[d:\\vnstock DB - {len(vnstock_tables)} tables]:")
for t, c in sorted(vnstock_tables.items()):
    print(f"  {t:55s}: {c:>12,d} rows")

print(f"\n[d:\\VESTA DB - {len(vesta_tables)} tables]:")
for t, c in sorted(vesta_tables.items()):
    print(f"  {t:55s}: {c:>12,d} rows")

# 2. Comparison for Symbol 'VIC'
print("\n" + "="*80)
print("2. DETAILED DATA COMPARISON FOR SYMBOL: 'VIC'")
print("="*80)

# Check dim_symbol
print("\n--- A. Master Reference (dim_symbol) for VIC ---")
vic_vnstock_dim = con_vnstock.execute("SELECT * FROM core.dim_symbol WHERE symbol = 'VIC'").df()
vic_vesta_dim = con_vesta.execute("SELECT * FROM core.dim_symbol WHERE symbol = 'VIC'").df()
print("vnstock dim_symbol columns:", list(vic_vnstock_dim.columns))
print("vnstock dim_symbol data:\n", vic_vnstock_dim.to_dict(orient="records"))
print("\nVESTA dim_symbol columns:", list(vic_vesta_dim.columns))
print("VESTA dim_symbol data:\n", vic_vesta_dim.to_dict(orient="records"))

# Check OHLCV
print("\n--- B. Market OHLCV Daily for VIC ---")
vic_vnstock_ohlcv_meta = con_vnstock.execute("""
    SELECT MIN(trading_date) as min_date, MAX(trading_date) as max_date, COUNT(*) as cnt, 
           AVG(close) as avg_close, MIN(close) as min_close, MAX(close) as max_close
    FROM core.market_ohlcv_daily WHERE symbol = 'VIC'
""").df()
vic_vesta_ohlcv_meta = con_vesta.execute("""
    SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt, 
           AVG(close) as avg_close, MIN(close) as min_close, MAX(close) as max_close
    FROM core.market_ohlcv_daily WHERE symbol = 'VIC'
""").df()
print("vnstock OHLCV summary (10-year backfill):\n", vic_vnstock_ohlcv_meta.to_dict(orient="records")[0])
print("VESTA OHLCV summary (100-day test crawl):\n", vic_vesta_ohlcv_meta.to_dict(orient="records")[0])

# Check corporate events
print("\n--- C. Corporate Events for VIC ---")
vic_vnstock_events = con_vnstock.execute("""
    SELECT COUNT(*) as total_events, 
           MIN(event_date) as min_d, MAX(event_date) as max_d
    FROM core.corporate_events WHERE symbol = 'VIC'
""").df()
vic_vesta_events = con_vesta.execute("""
    SELECT COUNT(*) as total_events, 
           MIN(event_date) as min_d, MAX(event_date) as max_d
    FROM core.corporate_events WHERE symbol = 'VIC'
""").df()
print("vnstock corporate_events summary:\n", vic_vnstock_events.to_dict(orient="records")[0])
print("VESTA corporate_events summary:\n", vic_vesta_events.to_dict(orient="records")[0])

# Check Fundamentals
print("\n--- D. Fundamentals for VIC ---")
print("vnstock fundamental tables (5 separate core tables):")
for t in ["fundamental_balance_sheet", "fundamental_income_statement", "fundamental_cash_flow", "fundamental_ratio", "fundamental_financial_health_score"]:
    full_t = f"core.{t}"
    if full_t in vnstock_tables:
        res = con_vnstock.execute(f"SELECT COUNT(*) as cnt, MIN(period) as min_p, MAX(period) as max_p FROM {full_t} WHERE symbol = 'VIC'").df()
        print(f"  {full_t:45s}: {res.to_dict(orient='records')[0]}")

print("\nVESTA fundamental table (single unified core.fundamentals table):")
res_vesta_fund = con_vesta.execute("""
    SELECT report_type, COUNT(*) as cnt, MIN(period_end) as min_p, MAX(period_end) as max_p 
    FROM core.fundamentals 
    WHERE symbol = 'VIC' 
    GROUP BY report_type
""").df()
print(res_vesta_fund)

# Check News
print("\n--- E. News Data ---")
if "core.news" in vnstock_tables:
    vic_vnstock_news = con_vnstock.execute("SELECT COUNT(*) FROM core.news WHERE symbol = 'VIC'").fetchone()[0]
    print(f"vnstock core.news for VIC: {vic_vnstock_news} rows")
else:
    print("vnstock DB: NO NEWS CRAWLER / TABLE (Focused only on price + fundamental backfill).")

vic_vesta_news = con_vesta.execute("SELECT source, COUNT(*) as cnt FROM core.news WHERE symbol = 'VIC' GROUP BY source").df()
print("VESTA core.news for VIC (Dual-source Sentiment Engine):\n", vic_vesta_news.to_dict(orient="records"))

# Check Realtime Snapshot & Adjustments
print("\n--- F. Realtime Snapshot & Price Adjustments (VESTA exclusive) ---")
snap_cnt = con_vesta.execute("SELECT COUNT(*) FROM core.realtime_quote_snapshot WHERE symbol = 'VIC'").fetchone()[0]
adj_cnt = con_vesta.execute("SELECT COUNT(*) FROM core.price_adjustment_events WHERE symbol = 'VIC'").fetchone()[0]
print(f"VESTA realtime_quote_snapshot for VIC: {snap_cnt} rows")
print(f"VESTA price_adjustment_events for VIC: {adj_cnt} rows")

# Technical indicators feature store in vnstock
print("\n--- G. Feature Store in vnstock vs VESTA ---")
print(f"vnstock feature_store.technical table has {vnstock_tables.get('feature_store.technical', 0):,d} rows (SMA, RSI, MACD pre-calculated for all symbols).")
print("VESTA uses Point-in-Time (PIT) pipeline (F102) & PhoBERT NLP sentiment scoring rather than static TA tables.")
