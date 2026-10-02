import sys
sys.path.insert(0, 'src')
from etl import db

con = db.connect(read_only=True)
print("FPT news in con (snapshot_db):", con.execute("SELECT count(*) FROM core.news WHERE symbol = 'FPT'").fetchone()[0])
print("Total news in con (snapshot_db):", con.execute("SELECT count(*) FROM core.news").fetchone()[0])

con_news = db.connect_news(read_only=True)
print("FPT news in vesta_news.duckdb:", con_news_cnt := con_news.execute("SELECT count(*) FROM core.news WHERE symbol = 'FPT'").fetchone()[0])
print("Total news in vesta_news.duckdb:", con_news.execute("SELECT count(*) FROM core.news").fetchone()[0])

# Kiểm tra OHLCV
print("FPT ohlcv in con (snapshot_db):", con.execute("SELECT count(*) FROM core.market_ohlcv_daily WHERE symbol = 'FPT'").fetchone()[0])
con_ohlcv = db.connect_ohlcv(read_only=True)
print("FPT ohlcv in vesta_ohlcv.duckdb:", con_ohlcv.execute("SELECT count(*) FROM core.market_ohlcv_daily WHERE symbol = 'FPT'").fetchone()[0])
