import duckdb
import sys

sys.stdout.reconfigure(encoding="utf-8")

con_fresh = duckdb.connect("db/admin/vesta_crawled_fresh.duckdb", read_only=True)
con_ohlcv = duckdb.connect("db/admin/vesta_ohlcv.duckdb", read_only=True)

syms_fresh = con_fresh.execute("SELECT COUNT(DISTINCT symbol), COUNT(*) FROM core.market_ohlcv_daily").fetchone()
syms_ohlcv = con_ohlcv.execute("SELECT COUNT(DISTINCT symbol), COUNT(*) FROM core.market_ohlcv_daily").fetchone()

print(f"vesta_crawled_fresh: {syms_fresh[0]} symbols, {syms_fresh[1]:,} rows")
print(f"vesta_ohlcv:         {syms_ohlcv[0]} symbols, {syms_ohlcv[1]:,} rows")

# How many rows would we get if we MERGE them (UNION with deduplication)?
union_count = con_ohlcv.execute("""
    ATTACH 'db/admin/vesta_crawled_fresh.duckdb' AS fresh (READ_ONLY);
    SELECT COUNT(*) FROM (
        SELECT symbol, date FROM core.market_ohlcv_daily
        UNION
        SELECT symbol, date FROM fresh.core.market_ohlcv_daily
    );
""").fetchone()[0]

print(f"Merged unique (symbol, date) rows: {union_count:,}")

# Check NVL after merge
nvl_merged = con_ohlcv.execute("""
    SELECT COUNT(*), MIN(date), MAX(date) FROM (
        SELECT symbol, date FROM core.market_ohlcv_daily WHERE symbol='NVL'
        UNION
        SELECT symbol, date FROM fresh.core.market_ohlcv_daily WHERE symbol='NVL'
    );
""").fetchone()
print(f"NVL merged count: {nvl_merged[0]}, min={nvl_merged[1]}, max={nvl_merged[2]}")

con_fresh.close()
con_ohlcv.close()
