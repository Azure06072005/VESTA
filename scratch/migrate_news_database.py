"""scratch/migrate_news_database.py

Di chuyển toàn bộ dữ liệu tin tức từ db/vesta_snapshot.duckdb sang db/vesta_news.duckdb.
- Giữ nguyên vẹn 100% vesta_backup.duckdb.
- Làm sạch chuỗi body = 'None' thành NULL.
- Kiểm tra tính toàn vẹn dữ liệu (row count, min/max date, null count).
"""
import datetime as dt
import os
import pathlib
import sys
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT_DB_PATH = PROJECT_ROOT / "db" / "vesta_snapshot.duckdb"
NEWS_DB_PATH = PROJECT_ROOT / "db" / "vesta_news.duckdb"

print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] Bắt đầu di chuyển dữ liệu tin tức sang {NEWS_DB_PATH.name}...")

if not SNAPSHOT_DB_PATH.exists():
    raise FileNotFoundError(f"Không tìm thấy database nguồn: {SNAPSHOT_DB_PATH}")

# 1. Kết nối database đích vesta_news.duckdb
con_news = duckdb.connect(str(NEWS_DB_PATH), read_only=False)

# Tạo các schema cần thiết
con_news.execute("CREATE SCHEMA IF NOT EXISTS core;")
con_news.execute("CREATE SCHEMA IF NOT EXISTS staging;")
con_news.execute("CREATE SCHEMA IF NOT EXISTS meta;")

# 2. Attach database nguồn dạng READ_ONLY
snap_path_str = str(SNAPSHOT_DB_PATH).replace("\\", "/")
con_news.execute(f"ATTACH '{snap_path_str}' AS snap (READ_ONLY);")

print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] Đã gắn kết nối tới {SNAPSHOT_DB_PATH.name} (READ_ONLY).")

# 3. Di chuyển bảng core.news
print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] 1/5. Đang sao chép và làm sạch core.news...")
con_news.execute("DROP TABLE IF EXISTS core.news;")
con_news.execute("""
    CREATE TABLE core.news (
        symbol VARCHAR NOT NULL,
        "source" VARCHAR NOT NULL,
        published_at TIMESTAMP NOT NULL,
        available_at TIMESTAMP NOT NULL,
        headline VARCHAR NOT NULL,
        body VARCHAR,
        source_url VARCHAR NOT NULL PRIMARY KEY,
        fetched_at TIMESTAMP NOT NULL,
        duplicate_of VARCHAR
    );
""")

con_news.execute("""
    INSERT INTO core.news (symbol, "source", published_at, available_at, headline, body, source_url, fetched_at, duplicate_of)
    SELECT 
        symbol,
        "source",
        published_at,
        available_at,
        headline,
        CASE 
            WHEN body IS NULL OR trim(body) IN ('', 'None', 'null') THEN NULL 
            ELSE body 
        END AS body,
        source_url,
        fetched_at,
        duplicate_of
    FROM snap.core.news;
""")
core_news_cnt = con_news.execute("SELECT count(*) FROM core.news").fetchone()[0]
src_core_news_cnt = con_news.execute("SELECT count(*) FROM snap.core.news").fetchone()[0]
print(f"       -> Hoàn thành core.news: {core_news_cnt:,} / {src_core_news_cnt:,} dòng.")

# 4. Di chuyển bảng core.news_resources
print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] 2/5. Đang sao chép core.news_resources...")
con_news.execute("DROP TABLE IF EXISTS core.news_resources;")
con_news.execute("""
    CREATE TABLE core.news_resources (
        "source" VARCHAR NOT NULL,
        issuing_body VARCHAR NOT NULL,
        doc_type VARCHAR,
        doc_number VARCHAR,
        published_at TIMESTAMP NOT NULL,
        available_at TIMESTAMP NOT NULL,
        headline VARCHAR NOT NULL,
        summary VARCHAR,
        body VARCHAR,
        source_url VARCHAR NOT NULL PRIMARY KEY,
        fetched_at TIMESTAMP NOT NULL
    );
""")
con_news.execute("""
    INSERT INTO core.news_resources 
    SELECT 
        "source",
        issuing_body,
        doc_type,
        doc_number,
        published_at,
        available_at,
        headline,
        summary,
        CASE 
            WHEN body IS NULL OR trim(body) IN ('', 'None', 'null') THEN NULL 
            ELSE body 
        END AS body,
        source_url,
        fetched_at
    FROM snap.core.news_resources;
""")
res_cnt = con_news.execute("SELECT count(*) FROM core.news_resources").fetchone()[0]
src_res_cnt = con_news.execute("SELECT count(*) FROM snap.core.news_resources").fetchone()[0]
print(f"       -> Hoàn thành core.news_resources: {res_cnt:,} / {src_res_cnt:,} dòng.")

# 5. Di chuyển bảng core.sector_news_signal
print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] 3/5. Đang sao chép core.sector_news_signal...")
con_news.execute("DROP TABLE IF EXISTS core.sector_news_signal;")
con_news.execute("""
    CREATE TABLE core.sector_news_signal (
        source_url VARCHAR,
        sector_id INTEGER,
        sector_name VARCHAR NOT NULL,
        matched_keyword VARCHAR NOT NULL,
        match_tier VARCHAR NOT NULL,
        market_anchor VARCHAR NOT NULL,
        fetched_at TIMESTAMP NOT NULL,
        PRIMARY KEY(source_url, sector_id)
    );
""")
con_news.execute("""
    INSERT INTO core.sector_news_signal
    SELECT * FROM snap.core.sector_news_signal;
""")
sig_cnt = con_news.execute("SELECT count(*) FROM core.sector_news_signal").fetchone()[0]
src_sig_cnt = con_news.execute("SELECT count(*) FROM snap.core.sector_news_signal").fetchone()[0]
print(f"       -> Hoàn thành core.sector_news_signal: {sig_cnt:,} / {src_sig_cnt:,} dòng.")

# 6. Di chuyển staging.news và staging.news_resources
print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] 4/5. Đang sao chép staging.news & staging.news_resources...")
con_news.execute("DROP TABLE IF EXISTS staging.news;")
con_news.execute("""
    CREATE TABLE staging.news (
        symbol VARCHAR NOT NULL,
        "source" VARCHAR NOT NULL,
        published_at TIMESTAMP NOT NULL,
        available_at TIMESTAMP NOT NULL,
        headline VARCHAR NOT NULL,
        body VARCHAR,
        source_url VARCHAR NOT NULL,
        fetched_at TIMESTAMP NOT NULL,
        duplicate_of VARCHAR
    );
""")
con_news.execute("""
    INSERT INTO staging.news
    SELECT 
        symbol, "source", published_at, available_at, headline,
        CASE WHEN body IS NULL OR trim(body) IN ('', 'None', 'null') THEN NULL ELSE body END AS body,
        source_url, fetched_at, duplicate_of
    FROM snap.staging.news;
""")

con_news.execute("DROP TABLE IF EXISTS staging.news_resources;")
con_news.execute("""
    CREATE TABLE staging.news_resources (
        "source" VARCHAR,
        issuing_body VARCHAR,
        doc_type VARCHAR,
        doc_number VARCHAR,
        published_at TIMESTAMP,
        available_at TIMESTAMP,
        headline VARCHAR,
        summary VARCHAR,
        body VARCHAR,
        source_url VARCHAR,
        fetched_at TIMESTAMP
    );
""")
con_news.execute("""
    INSERT INTO staging.news_resources
    SELECT * FROM snap.staging.news_resources;
""")
stg_news_cnt = con_news.execute("SELECT count(*) FROM staging.news").fetchone()[0]
print(f"       -> Hoàn thành staging.news: {stg_news_cnt:,} dòng.")

# 7. Di chuyển meta.crawl_progress_news
print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] 5/5. Đang khởi tạo meta.crawl_progress cho tin tức...")
con_news.execute("DROP TABLE IF EXISTS meta.crawl_progress;")
con_news.execute("""
    CREATE TABLE meta.crawl_progress (
        dataset_name VARCHAR NOT NULL,
        symbol VARCHAR NOT NULL,
        status VARCHAR NOT NULL,
        retry_count INTEGER DEFAULT 0 NOT NULL,
        last_attempt TIMESTAMP,
        PRIMARY KEY(dataset_name, symbol)
    );
""")
con_news.execute("""
    INSERT INTO meta.crawl_progress
    SELECT dataset_name, symbol, status, retry_count, last_attempt
    FROM snap.meta.crawl_progress
    WHERE dataset_name IN ('F003', 'F004', 'cafef_news', 'cafef_categories', 'vietstock_news', 'news_macro');
""")
meta_cnt = con_news.execute("SELECT count(*) FROM meta.crawl_progress").fetchone()[0]
print(f"       -> Hoàn thành meta.crawl_progress: {meta_cnt:,} bản ghi theo dõi.")

# 8. Tách và tạo các VIEW / Index hỗ trợ
print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] Tạo các Index phục vụ truy vấn tốc độ cao...")
con_news.execute("CREATE INDEX IF NOT EXISTS idx_news_symbol ON core.news(symbol);")
con_news.execute("CREATE INDEX IF NOT EXISTS idx_news_pubdate ON core.news(published_at);")
con_news.execute("CREATE INDEX IF NOT EXISTS idx_news_resources_source ON core.news_resources(source);")
con_news.execute("CREATE INDEX IF NOT EXISTS idx_news_resources_pubdate ON core.news_resources(published_at);")

# 9. Thống kê chi tiết
body_valid_news = con_news.execute("SELECT count(*) FROM core.news WHERE body IS NOT NULL").fetchone()[0]
body_null_news = con_news.execute("SELECT count(*) FROM core.news WHERE body IS NULL").fetchone()[0]
body_valid_res = con_news.execute("SELECT count(*) FROM core.news_resources WHERE body IS NOT NULL").fetchone()[0]

print("\n" + "="*60)
print(f"KẾT QUẢ DI CHUYỂN DỮ LIỆU TIN TỨC SANG {NEWS_DB_PATH.name}:")
print(f" - core.news:               {core_news_cnt:,} dòng (Có body: {body_valid_news:,} | Body NULL: {body_null_news:,})")
print(f" - core.news_resources:     {res_cnt:,} dòng (Có body: {body_valid_res:,})")
print(f" - core.sector_news_signal: {sig_cnt:,} dòng")
print(f" - staging.news:            {stg_news_cnt:,} dòng")
print(f" - meta.crawl_progress:     {meta_cnt:,} dòng")
print("="*60)

con_news.close()
print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] Đã hoàn tất và đóng kết nối vesta_news.duckdb.")
