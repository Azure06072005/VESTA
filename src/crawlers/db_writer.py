"""src/crawlers/db_writer.py

Resilient DuckDB Writer & Synchronization Hub for VESTA.
Handles concurrency, process lock retries on Windows, and safe fallback buffering:
- Direct write to target database (default: db/vesta_snapshot.duckdb).
- If locked by another process (e.g. Antigravity IDE), writes to buffer database
  (db/vesta_crawled_fresh.duckdb or staging_sync.duckdb) and syncs when unlocked.
- Thread-safe & idempotent schema creation.
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys
import time
from typing import Any, Callable

import duckdb
import pandas as pd

logger = logging.getLogger("db_writer")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_TARGET_DB = str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb")
DEFAULT_BUFFER_DB = str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb")


class ResilientDuckDBWriter:
    """Bộ điều hợp ghi dữ liệu an toàn vào DuckDB, xử lý xung đột khóa file trên Windows."""

    def __init__(
        self,
        target_db: str = DEFAULT_TARGET_DB,
        buffer_db: str = DEFAULT_BUFFER_DB,
        max_retries: int = 5,
        retry_delay: float = 1.5,
    ) -> None:
        self.target_db = os.path.abspath(target_db)
        self.buffer_db = os.path.abspath(buffer_db)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        os.makedirs(os.path.dirname(self.target_db), exist_ok=True)
        os.makedirs(os.path.dirname(self.buffer_db), exist_ok=True)
        self._init_schemas(self.target_db)

    def _init_schemas(self, db_path: str) -> None:
        """Khởi tạo cấu trúc schema và các bảng cốt lõi (idempotent)."""
        ddl = """
        CREATE SCHEMA IF NOT EXISTS staging;
        CREATE SCHEMA IF NOT EXISTS core;
        CREATE SCHEMA IF NOT EXISTS meta;

        CREATE TABLE IF NOT EXISTS meta.crawl_progress (
            dataset_name  VARCHAR NOT NULL,
            symbol        VARCHAR NOT NULL,
            status        VARCHAR NOT NULL,
            retry_count   INTEGER NOT NULL DEFAULT 0,
            last_attempt  TIMESTAMP,
            PRIMARY KEY (dataset_name, symbol)
        );

        CREATE TABLE IF NOT EXISTS core.dim_symbol (
            symbol         VARCHAR NOT NULL PRIMARY KEY,
            organ_name     VARCHAR NOT NULL,
            en_organ_name  VARCHAR,
            exchange       VARCHAR,
            industry_code  VARCHAR,
            industry_name  VARCHAR,
            delisted_date  DATE,
            is_delisted    BOOLEAN,
            fetched_at     TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.market_ohlcv_daily (
            symbol      VARCHAR NOT NULL,
            date        DATE NOT NULL,
            open        DOUBLE,
            high        DOUBLE,
            low         DOUBLE,
            close       DOUBLE,
            volume      BIGINT,
            fetched_at  TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );

        CREATE TABLE IF NOT EXISTS core.fundamentals (
            symbol       VARCHAR NOT NULL,
            report_type  VARCHAR NOT NULL,
            period_end   DATE NOT NULL,
            available_at DATE NOT NULL,
            data_json    VARCHAR NOT NULL,
            fetched_at   TIMESTAMP NOT NULL,
            source       VARCHAR NOT NULL DEFAULT 'vnstock_data',
            PRIMARY KEY (symbol, report_type, period_end, fetched_at)
        );

        CREATE TABLE IF NOT EXISTS core.financial_notes (
            symbol        VARCHAR NOT NULL,
            period        VARCHAR NOT NULL,
            note_id       VARCHAR NOT NULL,
            note_name     VARCHAR,
            item_order    INTEGER,
            item_level    INTEGER,
            unit          VARCHAR,
            value         DOUBLE,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, period, note_id)
        );

        CREATE TABLE IF NOT EXISTS core.corporate_events (
            symbol       VARCHAR NOT NULL,
            event_id     VARCHAR NOT NULL,
            event_type   VARCHAR NOT NULL,
            event_date   DATE,
            detail_json  VARCHAR NOT NULL,
            fetched_at   TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, event_id)
        );

        CREATE TABLE IF NOT EXISTS core.stock_research_reports (
            report_id      VARCHAR,
            symbol         VARCHAR,
            broker         VARCHAR,
            title          VARCHAR NOT NULL,
            recommendation VARCHAR,
            target_price   DOUBLE,
            upside_pct     DOUBLE,
            report_date    DATE,
            report_url     VARCHAR PRIMARY KEY,
            pdf_url        VARCHAR,
            summary        TEXT,
            fetched_at     TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.proprietary_flow (
            symbol        VARCHAR NOT NULL,
            date          DATE NOT NULL,
            buy_vol       DOUBLE,
            buy_val       DOUBLE,
            sell_vol      DOUBLE,
            sell_val      DOUBLE,
            net_vol       DOUBLE,
            net_val       DOUBLE,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );

        CREATE TABLE IF NOT EXISTS core.market_foreign_flow_daily (
            symbol        VARCHAR NOT NULL,
            date          DATE NOT NULL,
            buy_volume    DOUBLE,
            sell_volume   DOUBLE,
            net_volume    DOUBLE,
            foreign_room  DOUBLE,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );

        CREATE TABLE IF NOT EXISTS core.macro_rates (
            rate_type     VARCHAR NOT NULL,
            term          VARCHAR NOT NULL,
            date          DATE NOT NULL,
            rate_value    DOUBLE NOT NULL,
            source        VARCHAR NOT NULL,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (rate_type, term, date)
        );

        CREATE TABLE IF NOT EXISTS core.news (
            symbol       VARCHAR NOT NULL,
            source       VARCHAR NOT NULL,
            published_at TIMESTAMP NOT NULL,
            available_at TIMESTAMP NOT NULL,
            headline     VARCHAR NOT NULL,
            body         VARCHAR,
            source_url   VARCHAR NOT NULL,
            fetched_at   TIMESTAMP NOT NULL,
            duplicate_of VARCHAR,
            PRIMARY KEY (source_url)
        );

        -- core.news_resources: Dành cho toàn bộ tin tức vĩ mô, báo chí tài chính, chính sách điều hành và hiệp hội ngành nghề
        CREATE TABLE IF NOT EXISTS core.news_resources (
            source        VARCHAR NOT NULL,
            issuing_body  VARCHAR NOT NULL,
            doc_type      VARCHAR,
            doc_number    VARCHAR,
            published_at  TIMESTAMP NOT NULL,
            available_at  TIMESTAMP NOT NULL,
            headline      VARCHAR NOT NULL,
            summary       VARCHAR,
            body          VARCHAR,
            source_url    VARCHAR NOT NULL,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (source_url)
        );

        -- Duy trì tương thích ngược với macro_policy
        CREATE TABLE IF NOT EXISTS core.macro_policy (
            source        VARCHAR NOT NULL,
            issuing_body  VARCHAR NOT NULL,
            doc_type      VARCHAR,
            doc_number    VARCHAR,
            published_at  TIMESTAMP NOT NULL,
            available_at  TIMESTAMP NOT NULL,
            headline      VARCHAR NOT NULL,
            summary       VARCHAR,
            body          VARCHAR,
            source_url    VARCHAR NOT NULL,
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (source_url)
        );

        CREATE TABLE IF NOT EXISTS core.cafef_disclosures (
            doc_id          VARCHAR NOT NULL PRIMARY KEY,
            symbol          VARCHAR NOT NULL,
            company_name    VARCHAR,
            trade_center_id INTEGER,
            exchange        VARCHAR,
            year            INTEGER,
            quarter         INTEGER,
            report_type     VARCHAR,
            content         VARCHAR,
            file_name       VARCHAR,
            file_url        VARCHAR,
            lnstctm         DOUBLE,
            published_at    TIMESTAMP,
            raw_json        VARCHAR,
            fetched_at      TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS staging.macro_economic_series (
            indicator     VARCHAR NOT NULL,
            sub_indicator VARCHAR NOT NULL,
            report_period VARCHAR NOT NULL,
            period_date   DATE,
            numeric_value DOUBLE,
            unit          VARCHAR,
            meta_json     VARCHAR,
            source        VARCHAR NOT NULL DEFAULT 'vnstock',
            fetched_at    TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.macro_economic_series (
            indicator     VARCHAR NOT NULL,
            sub_indicator VARCHAR NOT NULL,
            report_period VARCHAR NOT NULL,
            period_date   DATE,
            numeric_value DOUBLE,
            unit          VARCHAR,
            meta_json     VARCHAR,
            source        VARCHAR NOT NULL DEFAULT 'vnstock',
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (indicator, sub_indicator, report_period)
        );

        CREATE TABLE IF NOT EXISTS core.company_overview (
            symbol                 VARCHAR NOT NULL PRIMARY KEY,
            business_model         VARCHAR,
            founded_date           VARCHAR,
            charter_capital        DOUBLE,
            number_of_employees    INTEGER,
            listing_date           VARCHAR,
            par_value              DOUBLE,
            exchange               VARCHAR,
            listing_price          DOUBLE,
            listed_volume          BIGINT,
            ceo_name               VARCHAR,
            ceo_position           VARCHAR,
            inspector_name         VARCHAR,
            inspector_position     VARCHAR,
            establishment_license  VARCHAR,
            business_code          VARCHAR,
            tax_id                 VARCHAR,
            auditor                VARCHAR,
            company_type           VARCHAR,
            address                VARCHAR,
            phone                  VARCHAR,
            fax                    VARCHAR,
            email                  VARCHAR,
            website                VARCHAR,
            branches               VARCHAR,
            history                VARCHAR,
            free_float_percentage  DOUBLE,
            free_float             BIGINT,
            outstanding_shares     BIGINT,
            as_of_date             VARCHAR,
            source                 VARCHAR NOT NULL DEFAULT 'vnstock',
            fetched_at             TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.company_shareholders (
            symbol               VARCHAR NOT NULL,
            shareholder_name     VARCHAR NOT NULL,
            shares_owned         BIGINT,
            ownership_percentage DOUBLE,
            update_date          VARCHAR,
            source               VARCHAR NOT NULL DEFAULT 'vnstock',
            fetched_at           TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, shareholder_name)
        );
        """
        try:
            con = duckdb.connect(db_path, read_only=False)
            con.execute(ddl)
            con.close()
        except Exception as e:
            logger.debug("Không thể khởi tạo DDL trực tiếp trên %s: %s", db_path, e)
            # Khởi tạo trên buffer_db để dự phòng
            try:
                con_buf = duckdb.connect(self.buffer_db, read_only=False)
                con_buf.execute(ddl)
                con_buf.close()
            except Exception as e2:
                logger.warning("Không thể khởi tạo DDL trên buffer_db: %s", e2)

    def execute_with_retry(
        self,
        func: Callable[[duckdb.DuckDBPyConnection], Any],
        use_buffer_on_lock: bool = True,
    ) -> Any:
        """Thực thi một tác vụ cơ sở dữ liệu có kiểm soát khóa file và tự động dự phòng."""
        # Thử kết nối vào target_db trước
        for attempt in range(1, self.max_retries + 1):
            try:
                con = duckdb.connect(self.target_db, read_only=False)
                try:
                    res = func(con)
                    return res
                finally:
                    con.close()
            except Exception as e:
                err_str = str(e)
                is_lock = "Cannot open file" in err_str or "being used by another process" in err_str
                if is_lock:
                    if attempt < self.max_retries:
                        logger.warning(
                            "[Thử lại %d/%d] %s đang bị khóa bởi tiến trình khác. Chờ %.1fs...",
                            attempt,
                            self.max_retries,
                            os.path.basename(self.target_db),
                            self.retry_delay * attempt,
                        )
                        time.sleep(self.retry_delay * attempt)
                        continue
                    elif use_buffer_on_lock:
                        logger.warning(
                            "[FALLBACK] %s bị khóa hoàn toàn. Chuyển hướng lưu vào bộ đệm: %s",
                            os.path.basename(self.target_db),
                            os.path.basename(self.buffer_db),
                        )
                        con_buf = duckdb.connect(self.buffer_db, read_only=False)
                        try:
                            res = func(con_buf)
                            return res
                        finally:
                            con_buf.close()
                raise

    def sync_buffer_to_target(self) -> int:
        """Đồng bộ toàn bộ dữ liệu từ buffer_db vào target_db ngay khi khóa nhả (hỗ trợ retry và khớp cột động)."""
        if not os.path.exists(self.buffer_db):
            return 0

        con_tgt = None
        for attempt in range(1, self.max_retries + 1):
            try:
                con_tgt = duckdb.connect(self.target_db, read_only=False)
                break
            except Exception as e:
                err_str = str(e)
                is_lock = "Cannot open file" in err_str or "being used by another process" in err_str
                if is_lock and attempt < self.max_retries:
                    logger.info(
                        "[Đồng bộ bộ đệm %d/%d] %s đang bận, chờ %.1fs để thử lại...",
                        attempt,
                        self.max_retries,
                        os.path.basename(self.target_db),
                        self.retry_delay * attempt,
                    )
                    time.sleep(self.retry_delay * attempt)
                    continue
                else:
                    logger.info("Chưa thể đồng bộ bộ đệm: %s vẫn đang bị khóa (%s)", os.path.basename(self.target_db), e)
                    return 0

        if con_tgt is None:
            return 0

        try:
            con_tgt.execute(f"ATTACH '{self.buffer_db}' AS buffer_db;")
            # Dùng duckdb_tables() để truy vấn chính xác các bảng trong buffer_db
            tbl_rows = con_tgt.execute("""
                SELECT schema_name, table_name 
                FROM duckdb_tables() 
                WHERE database_name = 'buffer_db' AND schema_name IN ('core', 'main')
            """).fetchall()

            total_synced = 0
            curr_db = con_tgt.execute("SELECT current_database()").fetchone()[0]

            for schema_name, tbl in tbl_rows:
                try:
                    # Kiểm tra xem có bảng tương ứng trong core của target không
                    has_core = con_tgt.execute("""
                        SELECT count(*) 
                        FROM duckdb_tables() 
                        WHERE database_name = ? AND schema_name = 'core' AND table_name = ?
                    """, [curr_db, tbl]).fetchone()[0] > 0

                    if has_core:
                        # Khớp cột động giữa target và buffer để tránh lỗi schema mismatch
                        cols_tgt = [r[1] for r in con_tgt.execute(f"PRAGMA table_info('core.{tbl}')").fetchall()]
                        cols_buf = [r[1] for r in con_tgt.execute(f"PRAGMA table_info('buffer_db.{schema_name}.{tbl}')").fetchall()]
                        common_cols = [c for c in cols_tgt if c in cols_buf]
                        if common_cols:
                            cols_str = ", ".join(common_cols)
                            con_tgt.execute(f"""
                                INSERT OR IGNORE INTO core.{tbl} ({cols_str})
                                SELECT {cols_str} FROM buffer_db.{schema_name}.{tbl};
                            """)
                        con_tgt.execute(f"DELETE FROM buffer_db.{schema_name}.{tbl};")
                        total_synced += 1
                except Exception as ex:
                    logger.debug("Bỏ qua đồng bộ bảng %s.%s: %s", schema_name, tbl, ex)

            con_tgt.execute("DETACH buffer_db;")
            return total_synced
        finally:
            con_tgt.close()
