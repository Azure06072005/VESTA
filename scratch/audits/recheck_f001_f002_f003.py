import duckdb
import pandas as pd
import datetime as dt

con = duckdb.connect("db/vesta.duckdb", read_only=True)

print("=" * 80)
print("             VESTA SYSTEM AUDIT: F001, F001b, F002, F003")
print("=" * 80)

# -----------------------------------------------------------------------------
# F001 / F001b AUDIT
# -----------------------------------------------------------------------------
print("\n>>> [1] F001 & F001b: Master Symbol Universe Audit")
dim_count = con.execute("SELECT COUNT(*) FROM core.dim_symbol").fetchone()[0]
dim_cafef_count = con.execute("SELECT COUNT(*) FROM core.dim_symbol_cafef").fetchone()[0]

print(f"  * core.dim_symbol total rows:       {dim_count:6d}")
print(f"  * core.dim_symbol_cafef total rows: {dim_cafef_count:6d}")

print("\n  Exchange Breakdown in core.dim_symbol:")
dim_ex = con.execute("""
    SELECT exchange, is_delisted, COUNT(*) 
    FROM core.dim_symbol 
    GROUP BY exchange, is_delisted 
    ORDER BY COUNT(*) DESC
""").fetchall()
for ex, is_del, c in dim_ex:
    print(f"    - {str(ex):10s} (is_delisted={str(is_del):5s}): {c:5d} symbols")

# Check for any unexpected nulls or invalid exchanges
null_symbols = con.execute("SELECT COUNT(*) FROM core.dim_symbol WHERE symbol IS NULL OR exchange IS NULL").fetchone()[0]
invalid_ex = con.execute("SELECT COUNT(*) FROM core.dim_symbol WHERE exchange NOT IN ('HOSE', 'HNX', 'UPCOM', 'DELISTED')").fetchone()[0]
print(f"  * NULL symbol/exchange count:       {null_symbols} (expect 0)")
print(f"  * Invalid exchange count:           {invalid_ex} (expect 0)")

print("\n  Exchange Breakdown in core.dim_symbol_cafef (Supplement):")
cafef_ex = con.execute("""
    SELECT exchange, center_id, COUNT(*) 
    FROM core.dim_symbol_cafef 
    GROUP BY exchange, center_id 
    ORDER BY COUNT(*) DESC
""").fetchall()
for ex, cid, c in cafef_ex:
    print(f"    - {str(ex):10s} (center_id={cid:2d}): {c:5d} symbols")

# -----------------------------------------------------------------------------
# F002 AUDIT
# -----------------------------------------------------------------------------
print("\n>>> [2] F002: Market OHLCV Daily Audit")
ohlcv_count = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
ohlcv_symbols = con.execute("SELECT COUNT(DISTINCT symbol) FROM core.market_ohlcv_daily").fetchone()[0]
min_date, max_date = con.execute("SELECT MIN(date), MAX(date) FROM core.market_ohlcv_daily").fetchone()

print(f"  * Total OHLCV Daily Bars:           {ohlcv_count:10d}")
print(f"  * Distinct Symbols with OHLCV:      {ohlcv_symbols:6d}")
print(f"  * Date Range:                       {min_date} to {max_date}")

# Check for data quality issues (negative prices, nulls)
null_ohlcv = con.execute("""
    SELECT COUNT(*) FROM core.market_ohlcv_daily 
    WHERE symbol IS NULL OR date IS NULL OR open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL
""").fetchone()[0]
invalid_prices = con.execute("""
    SELECT COUNT(*) FROM core.market_ohlcv_daily 
    WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0 OR high < low
""").fetchone()[0]
print(f"  * NULL fields in OHLCV:             {null_ohlcv} (expect 0)")
print(f"  * Invalid price bars (H < L or <=0):{invalid_prices} (expect 0)")

# Progress status in meta.crawl_progress for F002
f002_progress = con.execute("""
    SELECT status, COUNT(*) FROM meta.crawl_progress 
    WHERE dataset_name = 'F002' 
    GROUP BY status
""").fetchall()
print("  * meta.crawl_progress F002 Status:")
for st, cnt in f002_progress:
    print(f"    - [{st:8s}]: {cnt:5d}")

# -----------------------------------------------------------------------------
# F003 AUDIT
# -----------------------------------------------------------------------------
print("\n>>> [3] F003: vnstock Corporate Announcements / News Audit")
news_vnstock_count = con.execute("SELECT COUNT(*) FROM core.news WHERE source = 'vnstock'").fetchone()[0]
news_vnstock_syms = con.execute("SELECT COUNT(DISTINCT symbol) FROM core.news WHERE source = 'vnstock'").fetchone()[0]
min_pub, max_pub = con.execute("SELECT MIN(published_at), MAX(published_at) FROM core.news WHERE source = 'vnstock'").fetchone()

print(f"  * Total vnstock News Rows:          {news_vnstock_count:10d}")
print(f"  * Distinct Symbols with News:       {news_vnstock_syms:6d}")
print(f"  * Published Date Range:             {min_pub} to {max_pub}")

null_headlines = con.execute("SELECT COUNT(*) FROM core.news WHERE source = 'vnstock' AND (headline IS NULL OR headline = '')").fetchone()[0]
null_source_urls = con.execute("SELECT COUNT(*) FROM core.news WHERE source = 'vnstock' AND (source_url IS NULL OR source_url = '')").fetchone()[0]
synthetic_urls = con.execute("SELECT COUNT(*) FROM core.news WHERE source = 'vnstock' AND source_url LIKE 'vnstock://%'").fetchone()[0]
body_filled = con.execute("SELECT COUNT(*) FROM core.news WHERE source = 'vnstock' AND body IS NOT NULL AND body != 'None' AND body != ''").fetchone()[0]

print(f"  * Missing/Empty Headlines:          {null_headlines} (expect 0)")
print(f"  * Missing/Empty source_urls:        {null_source_urls} (expect 0)")
print(f"  * Synthetic Fallback URIs:          {synthetic_urls} ({synthetic_urls/news_vnstock_count*100:.1f}%)")
print(f"  * Non-empty Real Body Text:         {body_filled} (0 confirmed - corporate disclosures)")

f003_progress = con.execute("""
    SELECT status, COUNT(*) FROM meta.crawl_progress 
    WHERE dataset_name = 'F003' 
    GROUP BY status
""").fetchall()
print("  * meta.crawl_progress F003 Status:")
for st, cnt in f003_progress:
    print(f"    - [{st:8s}]: {cnt:5d}")

con.close()
print("\n" + "=" * 80)
