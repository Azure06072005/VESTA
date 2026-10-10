import duckdb
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

mkt_p = "db/admin/vesta_market_index.duckdb"
ohlcv_p = "db/admin/vesta_ohlcv.duckdb"
news_p = "db/admin/vesta_news.duckdb"

con_mkt = duckdb.connect(mkt_p, read_only=True)
con_ohlcv = duckdb.connect(ohlcv_p, read_only=True)
con_news = duckdb.connect(news_p, read_only=True)

print("1. Checking sectors query:")
sectors_res = con_mkt.execute("""
    SELECT s.sector_id, s.sector_name, COUNT(DISTINCT sym.symbol) as symbol_count
    FROM core.dim_sector s
    LEFT JOIN core.dim_symbol_sector sym ON s.sector_id = sym.sector_id
    GROUP BY s.sector_id, s.sector_name
    ORDER BY symbol_count DESC
    LIMIT 12
""").fetchdf()
print(sectors_res)

print("\n2. Checking top movers from ohlcv:")
top_movers = con_ohlcv.execute("""
    WITH latest_date AS (
        SELECT MAX(date) as max_d FROM core.market_ohlcv_daily WHERE date <= CURRENT_DATE
    )
    SELECT symbol, close, (close - open)/NULLIF(open,0)*100 as pct, volume, (volume*close)/1e6 as val_mil
    FROM core.market_ohlcv_daily, latest_date
    WHERE date = max_d AND volume > 100000
    ORDER BY pct DESC
    LIMIT 5
""").fetchdf()
print(top_movers)

print("\n3. Checking global news:")
global_news = con_news.execute("""
    SELECT headline, source, published_at 
    FROM core.news 
    WHERE headline ILIKE '%Mỹ%' OR headline ILIKE '%Fed%' OR headline ILIKE '%thế giới%' OR headline ILIKE '%quốc tế%' OR headline ILIKE '%toàn cầu%'
    ORDER BY published_at DESC 
    LIMIT 5
""").fetchdf()
print(global_news)

con_mkt.close()
con_ohlcv.close()
con_news.close()
