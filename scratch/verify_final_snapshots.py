import duckdb
import sys
sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)

tables = [
    ("core.market_sentiment_snapshot", "Tâm lý & Độ rộng thị trường (Method 1)"),
    ("core.order_book_depth", "Sổ lệnh Level 2 Depth (VN100 - Vietcap)"),
    ("core.intraday_trades", "Khớp lệnh Intraday (VN100 - Vietcap)"),
    ("core.realtime_quote_snapshot", "Bảng giá Snapshot (1,751 mã - All Symbols)"),
    ("core.market_screener_snapshot", "Bộ lọc Đa Nhân Tố Chuyên Sâu (1,522 mã - All Symbols)"),
]

print("=== KIỂM TOÁN TỔNG THỂ 4 BẢNG SNAPSHOT NÂNG CẤP TRONG VESTA_SNAPSHOT ===")
for tbl, desc in tables:
    cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
    dates = con.execute(f"SELECT min(snapshot_date), max(snapshot_date) FROM {tbl}").fetchone() if "snapshot_date" in tbl else (None, None)
    symbols = con.execute(f"SELECT count(DISTINCT symbol) FROM {tbl}").fetchone()[0] if "symbol" in tbl else "N/A"
    print(f"\n📊 Bảng: [{tbl}] - {desc}")
    print(f"   • Tổng số bản ghi : {cnt:,} dòng")
    print(f"   • Số lượng mã     : {symbols}")
    if dates[0]:
        print(f"   • Phạm vi thời gian: {dates[0]} -> {dates[1]}")

con.close()
