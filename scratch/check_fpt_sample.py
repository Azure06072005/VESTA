import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)
row_1d = con.execute("SELECT min(date), max(date), count(*) FROM core.market_ohlcv_daily WHERE symbol='FPT'").fetchone()
print(f"FPT 1D: Start={row_1d[0]}, End={row_1d[1]}, Rows={row_1d[2]}")

row_1m = con.execute("SELECT min(time), max(time), count(*) FROM core.market_ohlcv_1m WHERE symbol='FPT'").fetchone()
print(f"FPT 1M (Snapshot DB): Start={row_1m[0]}, End={row_1m[1]}, Rows={row_1m[2]}")

# Kiểm tra cả HPG và VCB xem mã nào có số nến 1m dồi dào nhất
for s in ['HPG', 'VCB', 'SSI', 'MWG']:
    c1d = con.execute(f"SELECT count(*) FROM core.market_ohlcv_daily WHERE symbol='{s}'").fetchone()[0]
    c1m = con.execute(f"SELECT count(*) FROM core.market_ohlcv_1m WHERE symbol='{s}'").fetchone()[0]
    print(f"{s}: 1D={c1d:,} rows, 1M={c1m:,} rows")

