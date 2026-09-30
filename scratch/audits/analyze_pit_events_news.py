import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta_snapshot.duckdb', read_only=True)

print("="*90)
print("1. CHI TIẾT KHO SỰ KIỆN TIN TỨC DOANH NGHIỆP: core.pit_events (658,182 bản ghi)")
print("="*90)

cols = con.execute("PRAGMA table_info('core.pit_events')").fetchall()
for c in cols:
    print(f"  Col: {c[1]:25s} | Type: {c[2]:15s}")

count_total = con.execute("SELECT COUNT(*) FROM core.pit_events").fetchone()[0]
unique_syms = con.execute("SELECT COUNT(DISTINCT symbol) FROM core.pit_events").fetchone()[0]
date_min, date_max = con.execute("SELECT MIN(published_at), MAX(published_at) FROM core.pit_events").fetchone()
has_headline = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE headline IS NOT NULL AND LENGTH(TRIM(headline)) > 0").fetchone()[0]
has_url = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE source_url IS NOT NULL AND LENGTH(TRIM(source_url)) > 0").fetchone()[0]

print(f"\nThống kê core.pit_events:")
print(f"  - Tổng số tin tức sự kiện: {count_total:,} bài")
print(f"  - Số mã cổ phiếu: {unique_syms:,} mã")
print(f"  - Thời gian: {date_min} đến {date_max}")
print(f"  - Có headline: {has_headline:,} ({has_headline*100.0/count_total:.2f}%)")
print(f"  - Có source_url: {has_url:,} ({has_url*100.0/count_total:.2f}%)")

# Phân bổ nguồn URL trong core.pit_events
print("\nPhân bổ tên miền nguồn (Domain) trong core.pit_events:")
domain_stats = con.execute("""
    SELECT 
        CASE 
            WHEN source_url LIKE '%cafef.vn%' THEN 'cafef.vn'
            WHEN source_url LIKE '%vietstock.vn%' THEN 'vietstock.vn'
            WHEN source_url LIKE '%tinnhanhchungkhoan.vn%' THEN 'tinnhanhchungkhoan.vn'
            WHEN source_url LIKE '%vneconomy.vn%' THEN 'vneconomy.vn'
            WHEN source_url LIKE '%tuoitre.vn%' THEN 'tuoitre.vn'
            WHEN source_url LIKE '%baodautu.vn%' THEN 'baodautu.vn'
            WHEN source_url LIKE '%vnexpress.net%' THEN 'vnexpress.net'
            WHEN source_url IS NULL OR source_url = '' THEN 'EMPTY_OR_NULL'
            ELSE 'OTHER_DOMAINS'
        END as domain,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / COUNT(*), 2) as pct
    FROM core.pit_events
    GROUP BY 1
    ORDER BY count DESC
""").fetchall()

for d, c, p in domain_stats:
    print(f"  - {d:25s}: {c:>10,d} bài ({c*100.0/count_total:6.2f}%)")

con.close()
