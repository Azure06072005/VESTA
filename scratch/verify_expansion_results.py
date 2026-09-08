import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)

print("=========================================================================")
print(">>> BÁO CÁO XÁC MINH TOÀN DIỆN MỞ RỘNG YAHOO FINANCE (TỪ NĂM 2000) <<<")
print("=========================================================================")

# 1. Magnificent 7 Tech Stocks (core.market_global_equity_daily)
print("\n1. BẢNG CỔ PHIẾU CÔNG NGHỆ MỸ (core.market_global_equity_daily):")
total_mag7 = conn.execute("SELECT COUNT(*) FROM core.market_global_equity_daily").fetchone()[0]
print(f"   * Tổng số phiên giao dịch Mag7: {total_mag7:,}")

mag7_rows = conn.execute("""
    SELECT symbol, MIN(date) as start_d, MAX(date) as end_d, COUNT(*) as bars,
           ROUND(MIN(low), 2) as min_low, ROUND(MAX(high), 2) as max_high, ROUND(AVG(close), 2) as avg_close
    FROM core.market_global_equity_daily
    GROUP BY symbol
    ORDER BY symbol
""").fetchall()

for sym, s_d, e_d, bars, min_l, max_h, avg_c in mag7_rows:
    print(f"     - {sym:<6}: {s_d} -> {e_d} ({bars:,} phiên) | Low: ${min_l} -> High: ${max_h} | Close TB: ${avg_c}")

# 2. Asian Indices & Commodities (core.market_index_daily)
print("\n2. BẢNG CHỈ SỐ VĨ MÔ, HÀNG HÓA & NÔNG SẢN (core.market_index_daily):")
total_indices = conn.execute("SELECT COUNT(*) FROM core.market_index_daily").fetchone()[0]
print(f"   * Tổng số phiên giao dịch toàn bảng: {total_indices:,}")

all_indices = conn.execute("""
    SELECT index_code, MIN(date) as start_d, MAX(date) as end_d, COUNT(*) as bars
    FROM core.market_index_daily
    GROUP BY index_code
    ORDER BY bars DESC
""").fetchall()

for code, s_d, e_d, bars in all_indices:
    print(f"     - {code:<12}: {s_d} -> {e_d} ({bars:,} phiên)")

conn.close()
