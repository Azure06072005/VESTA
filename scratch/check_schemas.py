import sys
sys.path.insert(0, "src")
from etl import db

con = db.connect()
print("=== core.dim_symbol ===")
print(con.execute("PRAGMA table_info('core.dim_symbol')").df())
print("\n=== core.fundamentals ===")
print(con.execute("PRAGMA table_info('core.fundamentals')").df())
print("\n=== core.corporate_events ===")
print(con.execute("PRAGMA table_info('core.corporate_events')").df())
