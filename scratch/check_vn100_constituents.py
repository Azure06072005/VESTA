import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
vn100_symbols = con.execute("""
    SELECT DISTINCT symbol 
    FROM core.dim_index_constituents 
    WHERE index_code = 'VN100'
    ORDER BY symbol
""").fetchall()

symbols_list = [r[0] for r in vn100_symbols]
print(f"Tổng số mã trong rổ VN100 lấy từ core.dim_index_constituents: {len(symbols_list)}")
print(f"Mẫu 15 mã đầu: {symbols_list[:15]}")

con.close()
