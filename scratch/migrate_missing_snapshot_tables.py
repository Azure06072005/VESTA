import duckdb
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

snap_p = "db/admin/vesta_snapshot.duckdb"
ohlcv_p = "db/admin/vesta_ohlcv.duckdb"
mkt_p = "db/admin/vesta_market_index.duckdb"

print("1. Migrating intraday_trades and order_book_depth to vesta_ohlcv.duckdb...")
con_ohlcv = duckdb.connect(ohlcv_p, read_only=False)
con_ohlcv.execute(f"ATTACH '{snap_p}' AS snap (READ_ONLY);")

# core.intraday_trades
con_ohlcv.execute("""
    CREATE TABLE IF NOT EXISTS core.intraday_trades AS 
    SELECT * FROM snap.core.intraday_trades;
""")
cnt_trades = con_ohlcv.execute("SELECT COUNT(*) FROM core.intraday_trades").fetchone()[0]
print(f"   ✓ core.intraday_trades in vesta_ohlcv: {cnt_trades:,} rows")

# core.order_book_depth
con_ohlcv.execute("""
    CREATE TABLE IF NOT EXISTS core.order_book_depth AS 
    SELECT * FROM snap.core.order_book_depth;
""")
cnt_depth = con_ohlcv.execute("SELECT COUNT(*) FROM core.order_book_depth").fetchone()[0]
print(f"   ✓ core.order_book_depth in vesta_ohlcv: {cnt_depth:,} rows")

con_ohlcv.execute("CHECKPOINT;")
con_ohlcv.close()

print("2. Migrating foreign_flow_intraday, foreign_ownership_room, and training watermark to vesta_market_index.duckdb...")
con_mkt = duckdb.connect(mkt_p, read_only=False)
con_mkt.execute(f"ATTACH '{snap_p}' AS snap (READ_ONLY);")

con_mkt.execute("""
    CREATE TABLE IF NOT EXISTS core.foreign_flow_intraday AS 
    SELECT * FROM snap.core.foreign_flow_intraday;
""")
cnt_ffi = con_mkt.execute("SELECT COUNT(*) FROM core.foreign_flow_intraday").fetchone()[0]
print(f"   ✓ core.foreign_flow_intraday in vesta_market_index: {cnt_ffi:,} rows")

con_mkt.execute("""
    CREATE TABLE IF NOT EXISTS core.foreign_ownership_room AS 
    SELECT * FROM snap.core.foreign_ownership_room;
""")
cnt_for = con_mkt.execute("SELECT COUNT(*) FROM core.foreign_ownership_room").fetchone()[0]
print(f"   ✓ core.foreign_ownership_room in vesta_market_index: {cnt_for:,} rows")

con_mkt.execute("""
    CREATE TABLE IF NOT EXISTS meta.automated_training_watermark AS 
    SELECT * FROM snap.meta.automated_training_watermark;
""")
cnt_wm = con_mkt.execute("SELECT COUNT(*) FROM meta.automated_training_watermark").fetchone()[0]
print(f"   ✓ meta.automated_training_watermark in vesta_market_index: {cnt_wm:,} rows")

con_mkt.execute("CHECKPOINT;")
con_mkt.close()

# Synchronize to root db/ if possible
for p in [ohlcv_p, mkt_p]:
    root_dest = os.path.join("db", os.path.basename(p))
    try:
        shutil.copy2(p, root_dest)
        print(f"   ✓ Synced {p} -> {root_dest}")
    except Exception as e:
        print(f"   ℹ️ {root_dest} currently locked: {e}")

print("Migration complete!")
