"""scratch/research_f003_news.py

Nghiên cứu sâu dữ liệu tin tức F003 trong database vesta_snapshot.duckdb
"""
import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)

print("=" * 80)
print("1. CÁC BẢNG LIÊN QUAN ĐẾN TIN TỨC TRONG CSDL SNAPSHOT:")
tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_name LIKE '%news%'").fetchall()
for s, t in tables:
    cnt = con.execute(f"SELECT COUNT(*) FROM {s}.{t}").fetchone()[0]
    print(f"  • {s}.{t}: {cnt:,} dòng")

print("\n" + "=" * 80)
print("2. PHÂN TÍCH NGUỒN VÀ ĐỘ PHỦ BODY TRONG BẢNG core.news (F003 vs F004):")
q_news = """
SELECT 
    source,
    COUNT(*) as total_rows,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(CASE WHEN body IS NOT NULL AND length(trim(body)) > 0 THEN 1 END) as has_body,
    COUNT(CASE WHEN body IS NULL OR length(trim(body)) = 0 THEN 1 END) as empty_body,
    ROUND(COUNT(CASE WHEN body IS NULL OR length(trim(body)) = 0 THEN 1 END) * 100.0 / COUNT(*), 2) as empty_body_pct,
    MIN(published_at) as min_published,
    MAX(published_at) as max_published
FROM core.news
GROUP BY source
"""
df_news = con.execute(q_news).fetchdf()
print(df_news.to_string(index=False))

print("\n" + "=" * 80)
print("3. PHÂN TÍCH ĐỘ DÀI TRUNG BÌNH CỦA BODY TRONG core.news:")
q_len = """
SELECT 
    source,
    AVG(length(headline)) as avg_headline_len,
    AVG(length(body)) as avg_body_len,
    MAX(length(body)) as max_body_len,
    MIN(length(body)) as min_body_len
FROM core.news
WHERE body IS NOT NULL AND length(trim(body)) > 0
GROUP BY source
"""
df_len = con.execute(q_len).fetchdf()
print(df_len.to_string(index=False))

print("\n" + "=" * 80)
print("4. MẪU DỮ LIỆU F003 (vnstock) TRONG core.news:")
sample_vnstock = con.execute("""
    SELECT symbol, published_at, headline, substr(body, 1, 100) as body_sample, source_url
    FROM core.news
    WHERE source = 'vnstock'
    ORDER BY published_at DESC
    LIMIT 5
""").fetchdf()
print(sample_vnstock.to_string(index=False))

print("\n" + "=" * 80)
print("3b. KIỂM TRA CHÍNH XÁC NỘI DUNG CỦA BODY NGUỒN 'vnstock':")
q_none = """
SELECT 
    COUNT(*) as total_vnstock_news,
    COUNT(CASE WHEN body = 'None' THEN 1 END) as body_literal_string_None,
    COUNT(CASE WHEN body IS NULL THEN 1 END) as body_is_null,
    COUNT(CASE WHEN body IS NOT NULL AND body != 'None' AND length(trim(body)) > 4 THEN 1 END) as body_has_real_text
FROM core.news
WHERE source = 'vnstock'
"""
df_none = con.execute(q_none).fetchdf()
print(df_none.to_string(index=False))

print("\n" + "=" * 80)
print("5. PHÂN TÍCH BẢNG core.news_resources (SCHEMA VÀ DỮ LIỆU):")
cols_res = [c[0] for c in con.execute("DESCRIBE core.news_resources").fetchall()]
print("Columns in core.news_resources:", cols_res)

q_res_fixed = """
SELECT 
    source,
    COUNT(*) as total_rows,
    MIN(published_at) as min_published,
    MAX(published_at) as max_published
FROM core.news_resources
GROUP BY source
"""
df_res_fixed = con.execute(q_res_fixed).fetchdf()
print(df_res_fixed.to_string(index=False))

con.close()
