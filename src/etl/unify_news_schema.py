"""Module migration hợp nhất toàn bộ dữ liệu tin tức thành 1 schema duy nhất (Unified News Schema).

Tích hợp:
1. core.news (670,409 tin theo mã cổ phiếu)
2. core.news_resources (478,599 tin vĩ mô, báo chí tài chính, hiệp hội)
3. core.macro_policy (847 văn bản quy phạm và chính sách)

Thành một bảng duy nhất `core.news` với đầy đủ các trường:
- source_url: VARCHAR PRIMARY KEY
- news_type: VARCHAR ('EQUITY_STOCK', 'MACRO_POLICY', 'FINANCIAL_MEDIA', 'INDUSTRY_ASSOCIATION', 'GENERAL_NEWS')
- symbol: VARCHAR (Nullable; NULL cho tin vĩ mô)
- source: VARCHAR
- issuing_body: VARCHAR
- doc_type: VARCHAR
- doc_number: VARCHAR
- published_at: TIMESTAMP
- available_at: TIMESTAMP
- headline: VARCHAR
- summary: VARCHAR
- body: VARCHAR
- duplicate_of: VARCHAR
- fetched_at: TIMESTAMP

Đồng thời tạo các SQL Views tương thích ngược:
- core.news_resources (trỏ vào core.news WHERE symbol IS NULL)
- core.macro_policy (trỏ vào core.news WHERE news_type = 'MACRO_POLICY' OR source chính sách)
- core.v_stock_news (trỏ vào core.news WHERE symbol IS NOT NULL)
- core.v_macro_news (trỏ vào core.news WHERE symbol IS NULL)
"""
from __future__ import annotations

import logging
import pathlib
import sys
import time
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("unify_news_schema")

NEWS_DB_PATH = pathlib.Path(__file__).resolve().parents[2] / "db" / "vesta_news.duckdb"

def run_unification(db_path: pathlib.Path = NEWS_DB_PATH) -> dict:
    start_time = time.time()
    logger.info(f"Bắt đầu quy trình hợp nhất schema tin tức tại: {db_path}")
    
    con = duckdb.connect(str(db_path), read_only=False)
    
    # 1. Kiểm tra số lượng dòng hiện tại
    cnt_news = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
    cnt_res = con.execute("SELECT count(*) FROM core.news_resources").fetchone()[0]
    cnt_macro = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    logger.info(f"Hiện trạng ban đầu:")
    logger.info(f"  - core.news: {cnt_news:,} dòng")
    logger.info(f"  - core.news_resources: {cnt_res:,} dòng")
    logger.info(f"  - core.macro_policy: {cnt_macro:,} dòng")
    
    # 2. Tạo bảng tạm core.news_unified
    logger.info("Tạo bảng tạm core.news_unified...")
    con.execute("""
    CREATE TABLE IF NOT EXISTS core.news_unified (
        source_url     VARCHAR NOT NULL PRIMARY KEY,
        news_type      VARCHAR NOT NULL,
        symbol         VARCHAR,
        source         VARCHAR NOT NULL,
        issuing_body   VARCHAR,
        doc_type       VARCHAR,
        doc_number     VARCHAR,
        published_at   TIMESTAMP NOT NULL,
        available_at   TIMESTAMP NOT NULL,
        headline       VARCHAR NOT NULL,
        summary        VARCHAR,
        body           VARCHAR,
        duplicate_of   VARCHAR,
        fetched_at     TIMESTAMP NOT NULL
    );
    """)
    
    # Xóa sạch dữ liệu nếu bảng tạm đã tồn tại
    con.execute("DELETE FROM core.news_unified;")
    
    # 3. Nạp dữ liệu từ core.news (tin cổ phiếu)
    logger.info(f"Đang nạp {cnt_news:,} tin từ core.news vào news_unified...")
    con.execute("""
    INSERT INTO core.news_unified (
        source_url, news_type, symbol, source, issuing_body, doc_type, doc_number,
        published_at, available_at, headline, summary, body, duplicate_of, fetched_at
    )
    SELECT 
        source_url,
        'EQUITY_STOCK' AS news_type,
        symbol,
        source,
        NULL AS issuing_body,
        'EQUITY_NEWS' AS doc_type,
        NULL AS doc_number,
        published_at,
        available_at,
        headline,
        NULL AS summary,
        body,
        duplicate_of,
        fetched_at
    FROM core.news
    ON CONFLICT (source_url) DO NOTHING;
    """)
    n_after_news = con.execute("SELECT count(*) FROM core.news_unified").fetchone()[0]
    logger.info(f"-> Đã nạp thành công: {n_after_news:,} tin tức cổ phiếu.")
    
    # 4. Nạp dữ liệu từ core.news_resources (tin vĩ mô, báo chí, hiệp hội)
    logger.info(f"Đang nạp {cnt_res:,} tin từ core.news_resources vào news_unified...")
    con.execute("""
    INSERT INTO core.news_unified (
        source_url, news_type, symbol, source, issuing_body, doc_type, doc_number,
        published_at, available_at, headline, summary, body, duplicate_of, fetched_at
    )
    SELECT 
        source_url,
        CASE 
            WHEN source IN ('baochinhphu', 'ssc', 'mof', 'sbv', 'gdt', 'moit', 'moj') THEN 'MACRO_POLICY'
            WHEN source IN ('thoibaonganhang', 'thoibaotaichinh', 'vietnamfinance', 'tinnhanhchungkhoan', 'vneconomy', 'vietstock', 'baodautu') THEN 'FINANCIAL_MEDIA'
            WHEN source IN ('horea', 'vasep', 'vsa', 'vnba', 'vba', 'vita', 'vntextile', 'hoinongdan', 'hoidaukhi') THEN 'INDUSTRY_ASSOCIATION'
            ELSE 'GENERAL_NEWS'
        END AS news_type,
        NULL AS symbol,
        source,
        issuing_body,
        doc_type,
        doc_number,
        published_at,
        available_at,
        headline,
        summary,
        body,
        NULL AS duplicate_of,
        fetched_at
    FROM core.news_resources
    ON CONFLICT (source_url) DO NOTHING;
    """)
    n_after_res = con.execute("SELECT count(*) FROM core.news_unified").fetchone()[0]
    logger.info(f"-> Tổng sau khi nạp news_resources: {n_after_res:,} tin (đã khử trùng lặp).")
    
    # 5. Nạp dữ liệu từ core.macro_policy (bổ sung các văn bản còn thiếu)
    logger.info(f"Đang nạp {cnt_macro:,} văn bản từ core.macro_policy...")
    con.execute("""
    INSERT INTO core.news_unified (
        source_url, news_type, symbol, source, issuing_body, doc_type, doc_number,
        published_at, available_at, headline, summary, body, duplicate_of, fetched_at
    )
    SELECT 
        source_url,
        'MACRO_POLICY' AS news_type,
        NULL AS symbol,
        source,
        issuing_body,
        doc_type,
        doc_number,
        published_at,
        available_at,
        headline,
        summary,
        body,
        NULL AS duplicate_of,
        fetched_at
    FROM core.macro_policy
    ON CONFLICT (source_url) DO NOTHING;
    """)
    n_total_unified = con.execute("SELECT count(*) FROM core.news_unified").fetchone()[0]
    logger.info(f"-> Tổng số lượng bài viết duy nhất trong news_unified: {n_total_unified:,} dòng.")
    
    # 6. Kiểm tra an toàn trước khi chuyển đổi
    if n_total_unified < cnt_news or n_total_unified < cnt_res:
        raise ValueError(f"Dữ liệu hợp nhất ({n_total_unified:,}) nhỏ hơn bảng nguồn! Hủy bỏ để bảo vệ an toàn dữ liệu.")
    
    # 7. Hoán đổi bảng và thiết lập View tương thích ngược
    logger.info("Thực hiện hoán đổi bảng và thiết lập View tương thích ngược...")
    con.execute("DROP TABLE core.macro_policy;")
    con.execute("DROP TABLE core.news_resources;")
    con.execute("DROP TABLE core.news;")
    con.execute("ALTER TABLE core.news_unified RENAME TO news;")
    
    # Tạo Views tương thích ngược
    logger.info("Tạo Views tương thích ngược...")
    con.execute("""
    CREATE OR REPLACE VIEW core.news_resources AS
    SELECT 
        source, 
        issuing_body, 
        doc_type, 
        doc_number, 
        published_at, 
        available_at, 
        headline, 
        summary, 
        body, 
        source_url, 
        fetched_at
    FROM core.news
    WHERE symbol IS NULL;
    """)
    
    con.execute("""
    CREATE OR REPLACE VIEW core.macro_policy AS
    SELECT 
        source, 
        issuing_body, 
        doc_type, 
        doc_number, 
        published_at, 
        available_at, 
        headline, 
        summary, 
        body, 
        source_url, 
        fetched_at
    FROM core.news
    WHERE news_type = 'MACRO_POLICY' OR (symbol IS NULL AND source IN ('baochinhphu', 'ssc', 'mof', 'sbv', 'gdt', 'moit', 'thoibaonganhang'));
    """)
    
    con.execute("""
    CREATE OR REPLACE VIEW core.v_stock_news AS
    SELECT * FROM core.news WHERE symbol IS NOT NULL;
    """)
    
    con.execute("""
    CREATE OR REPLACE VIEW core.v_macro_news AS
    SELECT * FROM core.news WHERE symbol IS NULL;
    """)
    
    # Đồng bộ hóa staging.news (cho phép symbol NULL)
    logger.info("Đồng bộ hóa schema staging.news...")
    con.execute("""
    CREATE TABLE IF NOT EXISTS staging.news_unified (
        source_url     VARCHAR,
        news_type      VARCHAR,
        symbol         VARCHAR,
        source         VARCHAR,
        issuing_body   VARCHAR,
        doc_type       VARCHAR,
        doc_number     VARCHAR,
        published_at   TIMESTAMP,
        available_at   TIMESTAMP,
        headline       VARCHAR,
        summary        VARCHAR,
        body           VARCHAR,
        duplicate_of   VARCHAR,
        fetched_at     TIMESTAMP
    );
    """)
    con.execute("""
    INSERT INTO staging.news_unified
    SELECT 
        source_url,
        'EQUITY_STOCK' AS news_type,
        symbol,
        source,
        NULL AS issuing_body,
        'EQUITY_NEWS' AS doc_type,
        NULL AS doc_number,
        published_at,
        available_at,
        headline,
        NULL AS summary,
        body,
        duplicate_of,
        fetched_at
    FROM staging.news;
    """)
    con.execute("DROP TABLE IF EXISTS staging.news_resources;")
    con.execute("DROP TABLE IF EXISTS staging.macro_policy;")
    con.execute("DROP TABLE staging.news;")
    con.execute("ALTER TABLE staging.news_unified RENAME TO news;")
    
    con.execute("""
    CREATE OR REPLACE VIEW staging.news_resources AS
    SELECT 
        source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
    FROM staging.news
    WHERE symbol IS NULL;
    """)
    con.execute("""
    CREATE OR REPLACE VIEW staging.macro_policy AS
    SELECT 
        source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
    FROM staging.news
    WHERE news_type = 'MACRO_POLICY' OR (symbol IS NULL AND source IN ('baochinhphu', 'ssc', 'mof', 'sbv', 'gdt', 'moit', 'thoibaonganhang'));
    """)

    # Kiểm tra xác thực sau chuyển đổi
    final_news_cnt = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
    final_stock_cnt = con.execute("SELECT count(*) FROM core.v_stock_news").fetchone()[0]
    final_macro_cnt = con.execute("SELECT count(*) FROM core.v_macro_news").fetchone()[0]
    view_res_cnt = con.execute("SELECT count(*) FROM core.news_resources").fetchone()[0]
    view_macro_cnt = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    
    logger.info("=== KẾT QUẢ NGHIỆM THU SAU HỢP NHẤT ===")
    logger.info(f"  - Tổng bài viết trong core.news (Unified): {final_news_cnt:,}")
    logger.info(f"  - Số tin gắn mã cổ phiếu (core.v_stock_news): {final_stock_cnt:,}")
    logger.info(f"  - Số tin tức vĩ mô/ngành (core.v_macro_news): {final_macro_cnt:,}")
    logger.info(f"  - View tương thích core.news_resources: {view_res_cnt:,}")
    logger.info(f"  - View tương thích core.macro_policy: {view_macro_cnt:,}")
    
    con.close()
    elapsed = time.time() - start_time
    logger.info(f"Hoàn tất hợp nhất thành công trong {elapsed:.2f} giây!")
    
    return {
        "final_news_cnt": final_news_cnt,
        "final_stock_cnt": final_stock_cnt,
        "final_macro_cnt": final_macro_cnt,
        "view_res_cnt": view_res_cnt,
        "view_macro_cnt": view_macro_cnt,
        "elapsed_seconds": elapsed
    }

if __name__ == "__main__":
    run_unification()
