import duckdb
import pandas as pd
import json

con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)

# 1. Total symbols and exchanges in dim_symbol
print("=== DIM SYMBOL COVERAGE ===")
symbols_df = con.execute("""
    SELECT exchange, is_delisted, count(*) as count
    FROM core.dim_symbol
    GROUP BY exchange, is_delisted
    ORDER BY exchange, is_delisted
""").df()
print(symbols_df.to_string())

total_symbols = con.execute("SELECT count(distinct symbol) FROM core.dim_symbol").fetchone()[0]
print(f"\nTotal distinct symbols in core.dim_symbol: {total_symbols}")

# Check dim_symbol_cafef
cafef_symbols = con.execute("SELECT count(distinct symbol), count(*) FROM core.dim_symbol_cafef").fetchone()
print(f"Cafef OTC/Unlisted symbols: distinct={cafef_symbols[0]}, total={cafef_symbols[1]}")

# 2. Check coverage of symbols and dates across major core tables
queries = {
    "market_ohlcv_daily": ("core.market_ohlcv_daily", "symbol", "date"),
    "market_ohlcv_1m": ("core.market_ohlcv_1m", "symbol", "time"),
    "market_foreign_flow_daily": ("core.market_foreign_flow_daily", "symbol", "date"),
    "proprietary_flow": ("core.proprietary_flow", "symbol", "date"),
    "fundamentals": ("core.fundamentals", "symbol", None),
    "financial_notes": ("core.financial_notes", "symbol", None),
    "company_overview": ("core.company_overview", "symbol", None),
    "company_shareholders": ("core.company_shareholders", "symbol", None),
    "corporate_events": ("core.corporate_events", "symbol", "event_date"),
    "news": ("core.news", "symbol", "published_at"),
    "news_resources": ("core.news_resources", None, "published_at"),
    "pit_events": ("core.pit_events", "symbol", "published_at"),
    "stock_research_reports": ("core.stock_research_reports", "symbol", "report_date"),
    "market_index_daily": ("core.market_index_daily", "index_code", "date"),
    "macro_rates": ("core.macro_rates", None, "date"),
    "macro_economic_series": ("core.macro_economic_series", None, "period_date"),
    "order_book_depth": ("core.order_book_depth", "symbol", "timestamp"),
    "intraday_trades": ("core.intraday_trades", "symbol", "time"),
    "preprocessed.events": ("preprocessed.events", "symbol", "published_at"),
    "preprocessed.fundamentals_ratios": ("preprocessed.fundamentals_ratios", "symbol", None),
    "preprocessed.market_regimes": ("preprocessed.market_regimes", None, "date"),
    "preprocessed.macro_policy": ("preprocessed.macro_policy", None, "published_at")
}

summary_stats = []

for name, (tbl, sym_col, date_col) in queries.items():
    try:
        cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        sym_cnt = con.execute(f"SELECT count(distinct {sym_col}) FROM {tbl}").fetchone()[0] if sym_col else None
        
        if date_col:
            min_date, max_date = con.execute(f"SELECT min({date_col}), max({date_col}) FROM {tbl}").fetchone()
        else:
            min_date, max_date = None, None
            
        summary_stats.append({
            "table": tbl,
            "row_count": cnt,
            "distinct_symbols": sym_cnt,
            "min_date": str(min_date),
            "max_date": str(max_date)
        })
    except Exception as e:
        summary_stats.append({
            "table": tbl,
            "error": str(e)
        })

print("\n=== TABLE COVERAGE SUMMARY ===")
stats_df = pd.DataFrame(summary_stats)
print(stats_df.to_string())

with open("scratch/stats_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary_stats, f, ensure_ascii=False, indent=2)

con.close()
