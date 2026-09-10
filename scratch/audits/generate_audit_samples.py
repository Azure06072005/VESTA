import duckdb
import json
import datetime as dt

con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)

def default_serializer(obj):
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    return str(obj)

report = {}

# 1. Row counts & basic health
counts = {}
tables = [
    "core.dim_symbol",
    "core.dim_symbol_cafef",
    "core.market_ohlcv_daily",
    "core.news",
    "core.fundamentals",
    "core.corporate_events",
    "core.realtime_quote_snapshot",
    "meta.crawl_progress"
]

for t in tables:
    cnt = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    counts[t] = cnt

report["table_counts"] = counts

# Sub-counts
news_counts = con.execute("""
    SELECT 
        CASE 
            WHEN source_url LIKE 'vnstock://%' THEN 'vnstock_news (F003)'
            WHEN source_url LIKE 'https://cafef.vn%' THEN 'cafef_news (F004/b/c)'
            ELSE 'other_news'
        END as news_type,
        count(*) 
    FROM core.news 
    GROUP BY 1
""").fetchall()
report["news_counts"] = dict(news_counts)

fund_counts = con.execute("""
    SELECT report_type, source, count(*) 
    FROM core.fundamentals 
    GROUP BY 1, 2 
    ORDER BY 1, 2
""").fetchall()
report["fundamentals_breakdown"] = [
    {"report_type": r[0], "source": r[1], "count": r[2]} for r in fund_counts
]

corp_counts = con.execute("""
    SELECT event_type, count(*) 
    FROM core.corporate_events 
    GROUP BY 1 
    ORDER BY 2 DESC
""").fetchall()
report["corporate_events_types"] = dict(corp_counts)

progress_counts = con.execute("""
    SELECT dataset_name, status, count(*) 
    FROM meta.crawl_progress 
    GROUP BY 1, 2 
    ORDER BY 1, 2
""").fetchall()
report["crawl_progress"] = [
    {"dataset": r[0], "status": r[1], "count": r[2]} for r in progress_counts
]

# 2. Extract 1 representative sample from each dataset
samples = {}

# F001: dim_symbol
s_dim = con.execute("SELECT * FROM core.dim_symbol WHERE symbol = 'FPT'").fetch_df().to_dict(orient="records")
samples["F001_dim_symbol"] = s_dim[0] if s_dim else None

# F001b: dim_symbol_cafef
s_dim_cafef = con.execute("SELECT * FROM core.dim_symbol_cafef LIMIT 1").fetch_df().to_dict(orient="records")
samples["F001b_dim_symbol_cafef"] = s_dim_cafef[0] if s_dim_cafef else None

# F002: market_ohlcv_daily
s_ohlcv = con.execute("SELECT * FROM core.market_ohlcv_daily WHERE symbol = 'FPT' ORDER BY date DESC LIMIT 1").fetch_df().to_dict(orient="records")
samples["F002_market_ohlcv"] = s_ohlcv[0] if s_ohlcv else None

# F003: vnstock_news
s_vnnews = con.execute("SELECT * FROM core.news WHERE source_url LIKE 'vnstock://%' AND symbol = 'FPT' ORDER BY published_at DESC LIMIT 1").fetch_df().to_dict(orient="records")
samples["F003_vnstock_news"] = s_vnnews[0] if s_vnnews else None

# F004/b/c: cafef_news
s_cafefnews = con.execute("SELECT * FROM core.news WHERE source_url LIKE 'https://cafef.vn%' AND body IS NOT NULL AND length(body) > 200 ORDER BY published_at DESC LIMIT 1").fetch_df().to_dict(orient="records")
samples["F004_cafef_news"] = s_cafefnews[0] if s_cafefnews else None

# F005: fundamentals - vnstock_data
s_fund_vn = con.execute("SELECT * FROM core.fundamentals WHERE source = 'vnstock_data' AND symbol = 'FPT' AND report_type = 'income_statement' ORDER BY period_end DESC LIMIT 1").fetch_df().to_dict(orient="records")
if s_fund_vn:
    d = s_fund_vn[0]
    try:
        d["data_json"] = json.loads(d["data_json"])
    except Exception:
        pass
    samples["F005_fundamentals_vnstock"] = d

# F052: fundamentals - cafef (balance sheet)
s_fund_cf = con.execute("SELECT * FROM core.fundamentals WHERE source = 'cafef' AND symbol = 'HPG' AND report_type = 'balance_sheet' ORDER BY period_end DESC LIMIT 1").fetch_df().to_dict(orient="records")
if s_fund_cf:
    d = s_fund_cf[0]
    try:
        d["data_json"] = json.loads(d["data_json"])
    except Exception:
        pass
    samples["F052_fundamentals_cafef_bs"] = d

# F006: corporate_events
s_corp = con.execute("SELECT * FROM core.corporate_events WHERE event_type = 'DIVIDEND' AND symbol = 'FPT' ORDER BY event_date DESC LIMIT 1").fetch_df().to_dict(orient="records")
if s_corp:
    d = s_corp[0]
    try:
        d["detail_json"] = json.loads(d["detail_json"])
    except Exception:
        pass
    samples["F006_corporate_events"] = d

# F007: realtime_quote_snapshot
s_quote = con.execute("SELECT * FROM core.realtime_quote_snapshot WHERE symbol = 'FPT' LIMIT 1").fetch_df().to_dict(orient="records")
if s_quote:
    d = s_quote[0]
    try:
        d["snapshot_json"] = json.loads(d["snapshot_json"])
    except Exception:
        pass
    samples["F007_realtime_quote"] = d

# F008: crawl_progress
s_prog = con.execute("SELECT * FROM meta.crawl_progress WHERE status = 'success' ORDER BY last_attempt DESC LIMIT 1").fetch_df().to_dict(orient="records")
samples["F008_crawl_progress"] = s_prog[0] if s_prog else None

report["samples"] = samples

# 3. Data Quality Checks
dq = {}

# Completeness: Check nulls in primary keys
null_checks = {}
for t in ["core.dim_symbol", "core.market_ohlcv_daily", "core.news", "core.fundamentals", "core.corporate_events"]:
    cols = [r[0] for r in con.execute(f"DESCRIBE {t}").fetchall()]
    # Check null count across critical columns
    null_sql = " + ".join([f"count(CASE WHEN {c} IS NULL THEN 1 END)" for c in cols if c not in ('body', 'detail_json', 'duplicate_of', 'delisted_date')])
    total_nulls = con.execute(f"SELECT {null_sql} FROM {t}").fetchone()[0]
    null_checks[t] = total_nulls
dq["null_checks_in_required_columns"] = null_checks

# Timeliness / Range checks
ranges = {}
ranges["ohlcv_date_range"] = [str(d) for d in con.execute("SELECT min(date), max(date) FROM core.market_ohlcv_daily").fetchone()]
ranges["news_published_range"] = [str(d) for d in con.execute("SELECT min(published_at), max(published_at) FROM core.news").fetchone()]
ranges["fundamentals_period_range"] = [str(d) for d in con.execute("SELECT min(period_end), max(period_end) FROM core.fundamentals").fetchone()]
dq["date_ranges"] = ranges

# Uniqueness: Check for duplicate primary keys
duplicates = {}
dup_queries = {
    "dim_symbol": "SELECT count(*) FROM (SELECT symbol, count(*) FROM core.dim_symbol GROUP BY symbol HAVING count(*) > 1)",
    "market_ohlcv": "SELECT count(*) FROM (SELECT symbol, date, count(*) FROM core.market_ohlcv_daily GROUP BY symbol, date HAVING count(*) > 1)",
    "fundamentals": "SELECT count(*) FROM (SELECT symbol, report_type, period_end, fetched_at, count(*) FROM core.fundamentals GROUP BY symbol, report_type, period_end, fetched_at HAVING count(*) > 1)",
    "corporate_events": "SELECT count(*) FROM (SELECT event_id, count(*) FROM core.corporate_events GROUP BY event_id HAVING count(*) > 1)"
}
for k, q in dup_queries.items():
    duplicates[k] = con.execute(q).fetchone()[0]
dq["pk_duplicates"] = duplicates

report["data_quality"] = dq

with open("d:/VESTA/out/f001_f009_audit_summary.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, default=default_serializer, ensure_ascii=False)

print("Audit script finished successfully.")
