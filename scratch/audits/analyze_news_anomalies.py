import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

print("="*90)
print("PHÂN TÍCH CHI TIẾT CÁC LỖI DỮ LIỆU TIN TỨC: NULL BODY, GAPS VÀ ANOMALIES")
print("="*90)

# 1. Các nguồn có body bị NULL hoặc rỗng
missing_body_sources = con.execute("""
    SELECT source, COUNT(*) as total, 
           COUNT(CASE WHEN body IS NULL OR LENGTH(TRIM(body)) = 0 THEN 1 END) as missing_body,
           ROUND(COUNT(CASE WHEN body IS NULL OR LENGTH(TRIM(body)) = 0 THEN 1 END) * 100.0 / COUNT(*), 2) as missing_pct
    FROM core.macro_policy
    GROUP BY source
    HAVING COUNT(CASE WHEN body IS NULL OR LENGTH(TRIM(body)) = 0 THEN 1 END) > 0
    ORDER BY missing_body DESC
""").fetchall()

print("\n1. Nguồn bị THIẾU THÂN BÀI (NULL/Empty Body):")
if missing_body_sources:
    for s, tot, m, p in missing_body_sources:
        print(f"   - {s:25s}: Thiếu {m:>5,d} / {tot:>6,d} bài ({p:5.2f}%)")
else:
    print("   -> Tuyệt vời: Không có nguồn nào thiếu body!")

# 2. Các bản ghi có ngày xuất bản bất thường (published_at < 1990 hoặc > 2026-10-01)
print("\n2. Các bài viết có ngày xuất bản BẤT THƯỜNG (Date Anomalies):")
anomalies = con.execute("""
    SELECT source, headline, published_at, source_url
    FROM core.macro_policy
    WHERE published_at < '1990-01-01' OR published_at > '2026-10-01'
    ORDER BY published_at ASC
""").fetchall()

for a in anomalies:
    print(f"   - [{a[0]}] Ngày: {a[2]} | Tiêu đề: {str(a[1])[:45]} | URL: {a[3]}")

# 3. Phân tích độ dài trung bình của thân bài (Body Length) để phát hiện bài viết bị cắt cụt (Truncated Articles)
print("\n3. Thống kê độ dài trung bình thân bài (ký tự) của Top 15 nguồn:")
lengths = con.execute("""
    SELECT source, 
           ROUND(AVG(LENGTH(body)), 0) as avg_len,
           MIN(LENGTH(body)) as min_len,
           MAX(LENGTH(body)) as max_len,
           COUNT(CASE WHEN LENGTH(body) < 100 THEN 1 END) as short_body_count
    FROM core.macro_policy
    WHERE body IS NOT NULL
    GROUP BY source
    ORDER BY COUNT(*) DESC
    LIMIT 15
""").fetchall()

print(f"{'Source':25s} | {'Avg Len (chars)':15s} | {'Min Len':8s} | {'Max Len':10s} | {'Short (<100 chars)':18s}")
print("-" * 85)
for l in lengths:
    print(f"{l[0]:25s} | {l[1]:15,.0f} | {l[2]:8,d} | {l[3]:10,d} | {l[4]:18,d}")

con.close()
