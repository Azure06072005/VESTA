import duckdb
import pandas as pd
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

db_path = "db/vesta_latest_backup.duckdb"
con = duckdb.connect(db_path, read_only=True)

print("=" * 100)
print("1. TEMPORAL AUDIT: CORE.MARKET_OHLCV_DAILY")
print("=" * 100)
ohlcv_years = con.execute("""
    SELECT year(date) as yr, count(*) as row_cnt, count(distinct symbol) as symbol_cnt,
           min(date) as min_dt, max(date) as max_dt
    FROM core.market_ohlcv_daily
    GROUP BY yr
    ORDER BY yr
""").fetchdf()
print(ohlcv_years.to_string(index=False))

print("\n" + "=" * 100)
print("2. TEMPORAL AUDIT: CORE.NEWS (COMPANY-SPECIFIC EQUITY NEWS)")
print("=" * 100)
news_years = con.execute("""
    SELECT source, year(published_at) as yr, count(*) as article_cnt,
           min(published_at)::date as min_dt, max(published_at)::date as max_dt
    FROM core.news
    GROUP BY source, yr
    ORDER BY source, yr
""").fetchdf()
print(news_years.to_string(index=False))

print("\n" + "=" * 100)
print("3. TEMPORAL AUDIT: CORE.MACRO_POLICY BY SOURCE (DATE RANGES)")
print("=" * 100)
macro_sources = con.execute("""
    SELECT source, count(*) as total_articles,
           min(published_at)::date as min_dt, max(published_at)::date as max_dt,
           date_diff('day', min(published_at)::date, max(published_at)::date) as span_days
    FROM core.macro_policy
    GROUP BY source
    ORDER BY total_articles DESC
""").fetchdf()
print(macro_sources.to_string(index=False))

print("\n" + "=" * 100)
print("4. TEMPORAL AUDIT: CORE.MACRO_POLICY YEAR-BY-YEAR MATRIX (TOP SOURCES)")
print("=" * 100)
top_sources = [r[0] for r in con.execute("SELECT source FROM core.macro_policy GROUP BY source ORDER BY count(*) DESC LIMIT 8").fetchall()]
macro_matrix = con.execute(f"""
    SELECT year(published_at) as yr, source, count(*) as cnt
    FROM core.macro_policy
    WHERE source IN ({','.join([f"'{s}'" for s in top_sources])})
    GROUP BY yr, source
    ORDER BY yr, source
""").fetchdf()

pivot = macro_matrix.pivot(index="yr", columns="source", values="cnt").fillna(0).astype(int)
print(pivot.to_string())

print("\n" + "=" * 100)
print("5. TEMPORAL AUDIT: CORE.FUNDAMENTALS & CORPORATE_EVENTS")
print("=" * 100)
fun_years = con.execute("""
    SELECT report_type, year(period_end) as yr, count(*) as cnt
    FROM core.fundamentals
    GROUP BY report_type, yr
    ORDER BY report_type, yr
""").fetchdf()
print("Fundamentals year span:", con.execute("SELECT report_type, min(period_end), max(period_end), count(*) FROM core.fundamentals GROUP BY report_type").fetchdf().to_string(index=False))

events_years = con.execute("""
    SELECT min(event_date) as min_event, max(event_date) as max_event, count(*) as total_events
    FROM core.corporate_events
""").fetchdf()
print("Corporate Events span:\n", events_years.to_string(index=False))

con.close()
