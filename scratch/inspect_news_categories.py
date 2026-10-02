import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb
import re
from urllib.parse import urlparse

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)

print("=== CHECKING URL PATH PATTERNS (SECTIONS / CATEGORIES) ===")
# Let's inspect Tuổi Trẻ URL patterns
tt_urls = con.execute("""
    SELECT source_url, headline
    FROM core.news
    WHERE source = 'tuoitre'
    LIMIT 20
""").fetchall()

print("\n--- Tuổi Trẻ Sample URLs ---")
for u, h in tt_urls[:10]:
    print(f"URL: {u}\nHeadline: {h}\n")

# Let's inspect Tiền Phong Sample URLs
tp_urls = con.execute("""
    SELECT source_url, headline
    FROM core.news
    WHERE source = 'tienphong'
    LIMIT 10
""").fetchall()

print("\n--- Tiền Phong Sample URLs ---")
for u, h in tp_urls[:10]:
    print(f"URL: {u}\nHeadline: {h}\n")

# Let's aggregate categories from URLs if possible (path segment 1)
print("\n--- URL Path Segment 1 Analysis for Tuổi Trẻ ---")
tt_cats = con.execute("""
    SELECT 
        regexp_extract(source_url, 'https?://[^/]+/([^/]+)/', 1) as url_category,
        count(*) as count
    FROM core.news
    WHERE source = 'tuoitre'
    GROUP BY url_category
    ORDER BY count DESC
    LIMIT 25
""").df()
print(tt_cats.to_string())

print("\n--- URL Path Segment 1 Analysis for Tiền Phong ---")
tp_cats = con.execute("""
    SELECT 
        regexp_extract(source_url, 'https?://[^/]+/([^/]+)/', 1) as url_category,
        count(*) as count
    FROM core.news
    WHERE source = 'tienphong'
    GROUP BY url_category
    ORDER BY count DESC
    LIMIT 25
""").df()
print(tp_cats.to_string())

print("\n--- URL Path Segment 1 Analysis for Tin Nhanh Chung Khoan ---")
tnck_cats = con.execute("""
    SELECT 
        regexp_extract(source_url, 'https?://[^/]+/([^/]+)/', 1) as url_category,
        count(*) as count
    FROM core.news
    WHERE source = 'tinnhanhchungkhoan'
    GROUP BY url_category
    ORDER BY count DESC
    LIMIT 25
""").df()
print(tnck_cats.to_string())

con.close()
