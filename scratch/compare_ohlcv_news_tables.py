import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con_snap = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

print("=== OHLCV Tables in vesta_snapshot ===")
for tbl in ['core.market_ohlcv_daily', 'staging.market_ohlcv_daily', 'core.market_ohlcv_1m', 'core.market_index_daily']:
    try:
        cnt = con_snap.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {cnt:,} rows")
    except Exception as e:
        print(f"  {tbl}: {e}")

print("\n=== News Tables in vesta_snapshot ===")
for tbl in ['core.news', 'staging.news', 'core.news_resources', 'staging.news_resources', 'core.sector_news_signal']:
    try:
        cnt = con_snap.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {cnt:,} rows")
    except Exception as e:
        print(f"  {tbl}: {e}")

con_snap.close()

con_news = duckdb.connect('db/vesta_news.duckdb', read_only=True)
print("\n=== News Tables in vesta_news ===")
for tbl in ['core.news', 'staging.news', 'core.news_resources', 'staging.news_resources', 'core.sector_news_signal']:
    try:
        cnt = con_news.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {cnt:,} rows")
    except Exception as e:
        print(f"  {tbl}: {e}")
con_news.close()
