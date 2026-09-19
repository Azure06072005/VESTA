"""test_pipeline/scripts/audit_full_database_coverage.py

Comprehensive Audit of Crawled Market Data in VESTA DuckDB (2000 - Present).
Audits:
1. Overall table statistics and row counts.
2. Market OHLCV daily coverage (symbol universe, date ranges from 2000 to now).
3. Securities Sector (Công ty chứng khoán) deep dive: SSI, VND, VCI, HCM, SHS, MBS, FTS, CTS, BSI, VDS, AGR, ORS, etc.
4. Fundamentals coverage (Financial statements from 2018 to 2026).
5. News coverage and PIT events.
6. Newly added quantitative tables (proprietary flow, financial notes, macro rates).
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

# Key securities firms on HOSE, HNX, UPCOM
SECURITIES_SYMBOLS = [
    "SSI", "VND", "VCI", "HCM", "SHS", "MBS", "FTS", "CTS", "BSI", "VDS",
    "AGR", "ORS", "BVS", "TVS", "EVS", "APG", "WSS", "TCI", "SBS", "HBS",
    "VIG", "IVS", "PSI"
]

def run_audit(db_path: str = "db/vesta.duckdb"):
    print("=" * 80)
    print(f"DATABASE COVERAGE AUDIT: {db_path}")
    print("=" * 80)

    con = duckdb.connect(db_path, read_only=True)
    try:
        # 1. Table Row Counts
        print("\n--- 1. TABLE ROW COUNTS ---")
        tables = [
            "core.dim_symbol", "core.market_ohlcv_daily", "core.market_ohlcv_1m",
            "core.fundamentals", "core.corporate_events", "core.news",
            "core.macro_policy", "core.market_foreign_flow_daily",
            "core.market_index_daily", "core.pit_events"
        ]
        for tbl in tables:
            try:
                cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
                print(f"  {tbl:<30}: {cnt:>12,d} rows")
            except Exception as e:
                print(f"  {tbl:<30}: Error / Not found ({e})")

        # 2. Overall Market OHLCV Daily Span
        print("\n--- 2. OVERALL MARKET OHLCV DAILY SPAN ---")
        ohlcv_stats = con.execute("""
            SELECT 
                count(distinct symbol) as total_symbols,
                count(*) as total_rows,
                min(date) as min_date,
                max(date) as max_date
            FROM core.market_ohlcv_daily;
        """).df()
        print(ohlcv_stats.to_string(index=False))

        # 3. Dim Symbol vs OHLCV
        print("\n--- 3. UNIVERSE COVERAGE RATIO ---")
        dim_cnt = con.execute("SELECT count(distinct symbol) FROM core.dim_symbol").fetchone()[0]
        ohlcv_sym_cnt = ohlcv_stats['total_symbols'].iloc[0]
        print(f"  Total symbols in dim_symbol : {dim_cnt}")
        print(f"  Total symbols with OHLCV    : {ohlcv_sym_cnt} ({ohlcv_sym_cnt/dim_cnt*100:.1f}%)")

        # 4. Deep Dive: Securities Companies (Công ty chứng khoán)
        print("\n--- 4. SECURITIES COMPANIES (CÔNG TY CHỨNG KHOÁN) AUDIT ---")
        sec_sym_str = "', '".join(SECURITIES_SYMBOLS)
        
        # OHLCV coverage for securities firms
        sec_ohlcv = con.execute(f"""
            SELECT 
                symbol,
                count(*) as bar_count,
                min(date) as earliest_bar,
                max(date) as latest_bar
            FROM core.market_ohlcv_daily
            WHERE symbol IN ('{sec_sym_str}')
            GROUP BY symbol
            ORDER BY symbol;
        """).df()
        print("OHLCV Daily Coverage for Securities Firms:")
        print(sec_ohlcv.to_string(index=False))

        # Missing securities symbols in OHLCV
        crawled_sec = set(sec_ohlcv['symbol'].tolist()) if not sec_ohlcv.empty else set()
        missing_sec = set(SECURITIES_SYMBOLS) - crawled_sec
        print(f"\nSecurities symbols checked : {len(SECURITIES_SYMBOLS)}")
        print(f"Securities symbols present : {len(crawled_sec)}")
        print(f"Securities symbols missing : {sorted(list(missing_sec)) if missing_sec else 'NONE (100% Covered!)'}")

        # 5. Fundamentals coverage for securities firms
        print("\n--- 5. FUNDAMENTALS COVERAGE FOR SECURITIES FIRMS ---")
        sec_fun = con.execute(f"""
            SELECT 
                symbol,
                count(distinct period_end) as quarter_count,
                min(period_end) as earliest_period,
                max(period_end) as latest_period,
                count(*) as total_statement_rows
            FROM core.fundamentals
            WHERE symbol IN ('{sec_sym_str}')
            GROUP BY symbol
            ORDER BY symbol;
        """).df()
        print(sec_fun.head(10).to_string(index=False))
        fun_sec = set(sec_fun['symbol'].tolist()) if not sec_fun.empty else set()
        missing_fun_sec = set(SECURITIES_SYMBOLS) - fun_sec
        print(f"\nSecurities missing fundamentals: {sorted(list(missing_fun_sec)) if missing_fun_sec else 'NONE (100% Covered!)'}")

        # 6. News coverage for securities firms
        print("\n--- 6. NEWS COVERAGE FOR SECURITIES FIRMS ---")
        sec_news = con.execute(f"""
            SELECT 
                symbol,
                count(*) as article_count,
                min(published_at) as earliest_article,
                max(published_at) as latest_article
            FROM core.news
            WHERE symbol IN ('{sec_sym_str}')
            GROUP BY symbol
            ORDER BY article_count DESC;
        """).df()
        print(sec_news.head(10).to_string(index=False))

    finally:
        con.close()

if __name__ == "__main__":
    run_audit()
