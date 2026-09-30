import duckdb
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

db_path = 'db/vesta_snapshot.duckdb'
con = duckdb.connect(db_path, read_only=True)

print("="*90)
print("1. TỔNG QUAN HAI KHO DỮ LIỆU TIN TỨC: core.news (Micro) & core.macro_policy (Macro)")
print("="*90)

# 1. Khảo sát core.news
try:
    total_news = con.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
    news_sources = con.execute("""
        SELECT 
            source,
            COUNT(*) as total_rows,
            COUNT(DISTINCT symbol) as unique_symbols,
            COUNT(CASE WHEN body IS NOT NULL AND LENGTH(TRIM(body)) > 0 THEN 1 END) as has_body_count,
            ROUND(COUNT(CASE WHEN body IS NOT NULL AND LENGTH(TRIM(body)) > 0 THEN 1 END) * 100.0 / COUNT(*), 2) as body_pct,
            MIN(published_at) as min_date,
            MAX(published_at) as max_date
        FROM core.news
        GROUP BY source
        ORDER BY total_rows DESC
    """).fetchall()
    
    print(f"\n[A] KHO TIN TỨC VI MÔ DOANH NGHIỆP (core.news) - Tổng cộng: {total_news:,} bài")
    print(f"{'Source':20s} | {'Total Rows':12s} | {'Symbols':8s} | {'Has Body':10s} | {'Body %':8s} | {'Date Range':25s}")
    print("-" * 90)
    for s in news_sources:
        date_range = f"{str(s[5])[:10]} -> {str(s[6])[:10]}"
        print(f"{s[0]:20s} | {s[1]:12,d} | {s[2]:8,d} | {s[3]:10,d} | {s[4]:7.2f}% | {date_range:25s}")
except Exception as e:
    print(f"Lỗi kiểm tra core.news: {e}")

# 2. Khảo sát core.macro_policy
try:
    total_macro = con.execute("SELECT COUNT(*) FROM core.macro_policy").fetchone()[0]
    macro_sources = con.execute("""
        SELECT 
            source,
            COUNT(*) as total_rows,
            COUNT(CASE WHEN headline IS NOT NULL AND LENGTH(TRIM(headline)) > 0 THEN 1 END) as has_headline,
            COUNT(CASE WHEN body IS NOT NULL AND LENGTH(TRIM(body)) > 0 THEN 1 END) as has_body,
            ROUND(COUNT(CASE WHEN body IS NOT NULL AND LENGTH(TRIM(body)) > 0 THEN 1 END) * 100.0 / COUNT(*), 2) as body_pct,
            MIN(published_at) as min_date,
            MAX(published_at) as max_date
        FROM core.macro_policy
        GROUP BY source
        ORDER BY total_rows DESC
    """).fetchall()
    
    print(f"\n[B] KHO TIN TỨC VĨ MÔ & CHÍNH SÁCH NGÀNH (core.macro_policy) - Tổng cộng: {total_macro:,} bài")
    print(f"{'Rank':4s} | {'Source Name':25s} | {'Total Articles':15s} | {'Has Body':12s} | {'Body %':8s} | {'Date Range':25s}")
    print("-" * 95)
    for idx, s in enumerate(macro_sources, 1):
        date_range = f"{str(s[5])[:10] if s[5] else 'N/A'} -> {str(s[6])[:10] if s[6] else 'N/A'}"
        print(f"{idx:4d} | {s[0]:25s} | {s[1]:15,d} | {s[3]:12,d} | {s[4]:7.2f}% | {date_range:25s}")
except Exception as e:
    print(f"Lỗi kiểm tra core.macro_policy: {e}")

# 3. Khảo sát meta.crawl_progress để tìm lỗi forbidden / missing / failed
print("\n" + "="*90)
print("2. ĐIỀU TRA LỖI: FORBIDDEN REQUESTS, RATE LIMITS & THẤT BẠI TRONG meta.crawl_progress")
print("="*90)

try:
    progress_status = con.execute("""
        SELECT status, COUNT(*) 
        FROM meta.crawl_progress 
        GROUP BY status 
        ORDER BY COUNT(*) DESC
    """).fetchall()
    print("\nPhân bổ trạng thái trong meta.crawl_progress:")
    for st, count in progress_status:
        print(f"  - Trạng thái '{st}': {count:,} bản ghi")

    failed_records = con.execute("""
        SELECT dataset_name, symbol, status, retry_count, last_attempt, error_message
        FROM meta.crawl_progress
        WHERE status NOT IN ('SUCCESS', 'COMPLETED', 'DONE', 'UP_TO_DATE')
        ORDER BY last_attempt DESC
        LIMIT 50
    """).fetchall()
    
    if failed_records:
        print(f"\nDanh sách 50 trường hợp thất bại/lỗi gần nhất:")
        for r in failed_records[:20]:
            print(f"  Dataset: {r[0]:15s} | Symbol: {r[1]:6s} | Status: {r[2]:12s} | Retries: {r[3]} | Err: {str(r[5])[:50]}")
    else:
        print("\nKhông tìm thấy bản ghi lỗi trong meta.crawl_progress (hoặc tất cả đã SUCCESS).")

except Exception as e:
    print(f"Lỗi kiểm tra meta.crawl_progress: {e}")

con.close()
