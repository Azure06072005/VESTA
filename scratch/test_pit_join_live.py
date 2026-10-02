import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'src')
from pipeline import pit_join
from etl import db

con = db.connect(read_only=True)
tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core'").fetchall()]
print(f"Bang co trong connection hien tai: {len(tables)} bang")
print("Co 'market_ohlcv_daily'?", 'market_ohlcv_daily' in tables)
print("Co 'news'?", 'news' in tables)
print("Co 'pit_events'?", 'pit_events' in tables)

try:
    df = pit_join.build_events_for_symbol(con, 'FPT')
    print(f"So luong su kien FPT build duoc: {len(df)}")
except Exception as e:
    print(f"Loi khi build FPT: {e}")
