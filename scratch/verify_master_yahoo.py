import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)

print("=========================================================================")
print(">>> XÁC MINH DỮ LIỆU YAHOO FINANCE TRONG vesta_latest_backup.duckdb <<<")
print("=========================================================================")

# 1. News verification
news_cnt = conn.execute("SELECT COUNT(*) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()[0]
n_min, n_max = conn.execute("SELECT MIN(published_at), MAX(published_at) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()

print(f"\n1. core.macro_policy (Yahoo Finance News):")
print(f"   * Tổng số bài viết: {news_cnt:,}")
print(f"   * Khoảng thời gian: {n_min} -> {n_max}")

# News providers breakdown
print("   * Top 10 nguồn phát hành hàng đầu:")
providers = conn.execute("""
    SELECT issuing_body, COUNT(*) as cnt 
    FROM core.macro_policy 
    WHERE source = 'yahoo_finance' 
    GROUP BY issuing_body 
    ORDER BY cnt DESC 
    LIMIT 10
""").fetchall()
for p, c in providers:
    print(f"     - {p:<45}: {c:,} bài")

# 2. OHLCV verification
print(f"\n2. core.market_index_daily (Chuỗi nến lịch sử từ năm 2000):")
total_bars = conn.execute("SELECT COUNT(*) FROM core.market_index_daily").fetchone()[0]
print(f"   * Tổng số phiên giao dịch toàn bảng: {total_bars:,}")

indices = conn.execute("""
    SELECT index_code, MIN(date) as start_d, MAX(date) as end_d, COUNT(*) as bars
    FROM core.market_index_daily
    GROUP BY index_code
    ORDER BY bars DESC
""").fetchall()

print("   * Chi tiết từng chỉ số & tài sản vĩ mô:")
for code, s_d, e_d, bars in indices:
    print(f"     - {code:<12}: {s_d} -> {e_d} ({bars:,} phiên)")

conn.close()
