import duckdb
import glob

for p in glob.glob("db/*.duckdb") + glob.glob("db/admin/*.duckdb"):
    try:
        con = duckdb.connect(p, read_only=True, config={"access_mode": "read_only"})
        # Check if core.market_ohlcv_daily exists
        has_tbl = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='core' AND table_name='market_ohlcv_daily'").fetchone()[0]
        if has_tbl:
            row = con.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM core.market_ohlcv_daily WHERE symbol = 'NVL'").fetchone()
            total = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
            print(f"{p}: total={total:,}, NVL count={row[0]}, min={row[1]}, max={row[2]}")
        con.close()
    except Exception as e:
        print(f"Error {p}: {e}")
