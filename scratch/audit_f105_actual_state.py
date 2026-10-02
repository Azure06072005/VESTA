"""scratch/audit_f105_actual_state.py
Kịch bản khảo sát thực nghiệm số liệu thực tế cho Deep Research F105:
1. Thống kê vesta_news.duckdb: core.news, core.news_resources, core.news_entity_map, core.news_relevance_meta
2. Thống kê vesta_snapshot.duckdb: core.company_shareholders, core.company_overview, core.dim_symbol
3. Đánh giá tỷ lệ bài viết có symbol IS NULL theo từng nguồn báo
4. Thử nghiệm tốc độ và tỷ lệ nhận diện thực thể trên mẫu thực tế
"""
import os
import sys
import time
import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NEWS_DB = "db/vesta_news.duckdb"
SNAPSHOT_DB = "db/vesta_snapshot.duckdb"

print("=" * 70)
print("KHẢO SÁT SỐ LIỆU THỰC TẾ CHO DEEP RESEARCH F105")
print("=" * 70)

# 1. Khảo sát vesta_news.duckdb
con_news = duckdb.connect(NEWS_DB, read_only=True)
tables_news = [r[0] for r in con_news.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core';").fetchall()]
print(f"Các bảng trong vesta_news.duckdb: {tables_news}")

total_news = con_news.execute("SELECT COUNT(*) FROM core.news;").fetchone()[0]
null_symbol_news = con_news.execute("SELECT COUNT(*) FROM core.news WHERE symbol IS NULL OR trim(symbol) = '';").fetchone()[0]
tagged_symbol_news = con_news.execute("SELECT COUNT(*) FROM core.news WHERE symbol IS NOT NULL AND trim(symbol) != '';").fetchone()[0]

print(f"Tổng số bài viết trong core.news: {total_news:,}")
print(f"Số bài viết đã có symbol: {tagged_symbol_news:,} ({tagged_symbol_news/total_news*100:.2f}%)")
print(f"Số bài viết CÓ symbol IS NULL: {null_symbol_news:,} ({null_symbol_news/total_news*100:.2f}%)")

# Phân bổ bài viết theo source
print("\nPhân bổ bài viết theo source:")
df_sources = con_news.execute("""
    SELECT source, 
           COUNT(*) as total_count,
           SUM(CASE WHEN symbol IS NULL OR trim(symbol) = '' THEN 1 ELSE 0 END) as null_symbol_count,
           ROUND(SUM(CASE WHEN symbol IS NULL OR trim(symbol) = '' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as null_pct
    FROM core.news
    GROUP BY source
    ORDER BY total_count DESC;
""").df()
print(df_sources.to_string(index=False))

# Kiểm tra core.news_resources
if "news_resources" in tables_news:
    total_resources = con_news.execute("SELECT COUNT(*) FROM core.news_resources;").fetchone()[0]
    has_body_count = con_news.execute("SELECT COUNT(*) FROM core.news_resources WHERE body IS NOT NULL AND length(trim(body)) > 50;").fetchone()[0]
    print(f"\nTổng số bản ghi trong core.news_resources: {total_resources:,}")
    print(f"Số bài có body (> 50 ký tự): {has_body_count:,} ({has_body_count/total_resources*100:.2f}%)")
else:
    print("\nKhông tìm thấy bảng core.news_resources!")

# Kiểm tra core.news_entity_map và core.news_relevance_meta
has_entity_map = "news_entity_map" in tables_news
has_relevance_meta = "news_relevance_meta" in tables_news

print(f"\nBảng core.news_entity_map đã tồn tại: {has_entity_map}")
if has_entity_map:
    cnt_map = con_news.execute("SELECT COUNT(*) FROM core.news_entity_map;").fetchone()[0]
    cnt_unique_urls = con_news.execute("SELECT COUNT(DISTINCT source_url) FROM core.news_entity_map;").fetchone()[0]
    cnt_unique_symbols = con_news.execute("SELECT COUNT(DISTINCT symbol) FROM core.news_entity_map;").fetchone()[0]
    print(f"  - Số bản ghi ánh xạ: {cnt_map:,}")
    print(f"  - Số URL bài báo đã được ánh xạ: {cnt_unique_urls:,}")
    print(f"  - Số mã cổ phiếu được liên kết: {cnt_unique_symbols:,}")
    
    # Phân bổ theo entity_type
    df_types = con_news.execute("""
        SELECT entity_type, COUNT(*) as cnt, COUNT(DISTINCT symbol) as unique_symbols, COUNT(DISTINCT entity_name) as unique_names
        FROM core.news_entity_map
        GROUP BY entity_type;
    """).df()
    print("  - Phân bổ theo entity_type:")
    print(df_types.to_string(index=False))

print(f"\nBảng core.news_relevance_meta đã tồn tại: {has_relevance_meta}")
if has_relevance_meta:
    cnt_meta = con_news.execute("SELECT COUNT(*) FROM core.news_relevance_meta;").fetchone()[0]
    print(f"  - Số bản ghi siêu dữ liệu liên quan: {cnt_meta:,}")
    df_rel = con_news.execute("""
        SELECT relevance_category, is_financial_relevant, COUNT(*) as count,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as pct
        FROM core.news_relevance_meta
        GROUP BY relevance_category, is_financial_relevant
        ORDER BY count DESC;
    """).df()
    print("  - Phân bổ theo danh mục tính liên quan:")
    print(df_rel.to_string(index=False))

con_news.close()

# 2. Khảo sát vesta_snapshot.duckdb
print("\n" + "=" * 70)
con_snap = duckdb.connect(SNAPSHOT_DB, read_only=True)
tables_snap = [r[0] for r in con_snap.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core';").fetchall()]
print(f"Các bảng trong vesta_snapshot.duckdb: {len(tables_snap)} bảng")

cnt_shareholders = con_snap.execute("SELECT COUNT(*) FROM core.company_shareholders;").fetchone()[0]
cnt_unique_sh_names = con_snap.execute("SELECT COUNT(DISTINCT shareholder_name) FROM core.company_shareholders;").fetchone()[0]
print(f"Cổ đông lớn (core.company_shareholders): {cnt_shareholders:,} dòng, {cnt_unique_sh_names:,} tên duy nhất")

cnt_executives = con_snap.execute("SELECT COUNT(*) FROM core.company_overview WHERE ceo_name IS NOT NULL AND length(trim(ceo_name)) > 0;").fetchone()[0]
cnt_unique_execs = con_snap.execute("SELECT COUNT(DISTINCT ceo_name) FROM core.company_overview WHERE ceo_name IS NOT NULL;").fetchone()[0]
print(f"Ban điều hành/CEO (core.company_overview): {cnt_executives:,} dòng, {cnt_unique_execs:,} tên duy nhất")

cnt_symbols = con_snap.execute("SELECT COUNT(*) FROM core.dim_symbol;").fetchone()[0]
print(f"Doanh nghiệp niêm yết (core.dim_symbol): {cnt_symbols:,} mã")

con_snap.close()
print("=" * 70)
print("Hoàn tất khảo sát ban đầu.")
