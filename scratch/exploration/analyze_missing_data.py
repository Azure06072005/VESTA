import duckdb
import json
import pandas as pd

con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)

report = {}

# 1. Null counts per column across all core tables
null_analysis = {}
tables = [
    "core.dim_symbol",
    "core.dim_symbol_cafef",
    "core.market_ohlcv_daily",
    "core.news",
    "core.fundamentals",
    "core.corporate_events",
    "core.realtime_quote_snapshot",
    "core.macro_policy",
    "core.stock_research_reports",
    "core.market_foreign_flow_daily",
    "core.market_index_daily",
    "core.price_adjustment_events",
    "core.pit_events"
]

for t in tables:
    cols_desc = con.execute(f"DESCRIBE {t}").fetchall()
    total_rows = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    col_nulls = {}
    if total_rows > 0:
        for col_name, col_type, is_null, _, _, _ in cols_desc:
            null_count = con.execute(f"SELECT count(*) FROM {t} WHERE {col_name} IS NULL").fetchone()[0]
            if null_count > 0:
                col_nulls[col_name] = {
                    "null_count": null_count,
                    "null_pct": round(null_count / total_rows * 100, 2),
                    "type": col_type
                }
    null_analysis[t] = {
        "total_rows": total_rows,
        "null_columns": col_nulls
    }

report["null_analysis"] = null_analysis

# 2. Universe coverage gaps: 1,751 symbols in core.dim_symbol
dim_symbols = set(r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol").fetchall())
total_universe = len(dim_symbols)

coverage = {}
for t, col in [
    ("core.market_ohlcv_daily", "symbol"),
    ("core.news", "symbol"),
    ("core.fundamentals", "symbol"),
    ("core.corporate_events", "symbol"),
    ("core.realtime_quote_snapshot", "symbol"),
    ("core.market_foreign_flow_daily", "symbol"),
    ("core.stock_research_reports", "symbol")
]:
    covered = set(r[0] for r in con.execute(f"SELECT DISTINCT {col} FROM {t} WHERE {col} IS NOT NULL").fetchall())
    intersect = dim_symbols.intersection(covered)
    missing = dim_symbols - covered
    coverage[t] = {
        "covered_symbols_count": len(intersect),
        "coverage_pct": round(len(intersect) / total_universe * 100, 2),
        "missing_symbols_count": len(missing),
        "sample_missing": sorted(list(missing))[:15]
    }

report["universe_coverage"] = coverage

# 3. Fundamentals breakdown by report_type coverage
fund_cov = {}
for rtype in ["balance_sheet", "income_statement", "cash_flow", "ratio"]:
    symbols_with_rtype = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.fundamentals WHERE report_type = ?", [rtype]).fetchall())
    missing_rtype = dim_symbols - symbols_with_rtype
    fund_cov[rtype] = {
        "covered": len(symbols_with_rtype),
        "missing": len(missing_rtype),
        "pct": round(len(symbols_with_rtype) / total_universe * 100, 2)
    }
report["fundamentals_coverage"] = fund_cov

# 4. News body completeness
news_body_stats = con.execute("""
    SELECT 
        CASE 
            WHEN source_url LIKE 'vnstock://%' THEN 'vnstock'
            WHEN source_url LIKE 'https://cafef.vn%' THEN 'cafef'
            ELSE 'other'
        END as source_category,
        count(*) as total,
        count(body) as with_body,
        count(*) - count(body) as null_body,
        round((count(*) - count(body)) * 100.0 / count(*), 2) as null_body_pct
    FROM core.news
    GROUP BY 1
""").fetchall()
report["news_body_completeness"] = [
    {"source": r[0], "total": r[1], "with_body": r[2], "null_body": r[3], "null_pct": r[4]} for r in news_body_stats
]

# 5. crawl_progress failures root causes
prog_failures = con.execute("""
    SELECT dataset_name, status, count(*) 
    FROM meta.crawl_progress 
    WHERE status != 'success' 
    GROUP BY 1, 2 
    ORDER BY 1, 2
""").fetchall()
report["crawl_progress_failures"] = [
    {"dataset": r[0], "status": r[1], "count": r[2]} for r in prog_failures
]

# Sample failed symbols in meta.crawl_progress for each dataset
failed_samples = {}
for ds in ["F002", "F003", "F004", "F005", "F006", "F007"]:
    rows = con.execute("SELECT symbol, status, retry_count FROM meta.crawl_progress WHERE dataset_name = ? AND status != 'success' LIMIT 5", [ds]).fetchall()
    failed_samples[ds] = [{"symbol": r[0], "status": r[1], "retries": r[2]} for r in rows]
report["failed_samples"] = failed_samples

# Check characteristics of symbols missing from OHLCV or Fundamentals
missing_ohlcv_syms = list(dim_symbols - set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.market_ohlcv_daily").fetchall()))
if missing_ohlcv_syms:
    exchange_dist = con.execute("SELECT exchange, is_delisted, count(*) FROM core.dim_symbol WHERE symbol IN ? GROUP BY 1, 2", [missing_ohlcv_syms]).fetchall()
    report["missing_ohlcv_characteristics"] = [
        {"exchange": r[0], "is_delisted": r[1], "count": r[2]} for r in exchange_dist
    ]

with open("d:/VESTA/out/missing_data_deep_dive.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, default=str, ensure_ascii=False)

print("Missing data analysis completed.")
