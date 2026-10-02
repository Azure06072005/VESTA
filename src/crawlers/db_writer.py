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
DEFAULT_BACKUP_DB = str(PROJECT_ROOT / "db" / "vesta_backup.duckdb")


class ResilientDuckDBWriter:
    """Bộ điều hợp ghi dữ liệu an toàn vào DuckDB, xử lý xung đột khóa file trên Windows."""

    def __init__(
        self,
        target_db: str = DEFAULT_TARGET_DB,
        buffer_db: str = DEFAULT_BUFFER_DB,
        max_retries: int = 5,
        retry_delay: float = 1.5,
        buffer_first: bool = False,
    ) -> None:
        self.target_db = os.path.abspath(target_db)
        self.buffer_db = os.path.abspath(buffer_db)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.buffer_first = buffer_first

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

        CREATE TABLE IF NOT EXISTS staging.market_ohlcv_daily (
            symbol      VARCHAR NOT NULL,
            date        DATE NOT NULL,
            open        DOUBLE,
            high        DOUBLE,
            low         DOUBLE,
            close       DOUBLE,
            volume      BIGINT,
            fetched_at  TIMESTAMP NOT NULL
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
        CREATE TABLE IF NOT EXISTS staging.news (
            source_url   VARCHAR,
            news_type    VARCHAR,
            symbol       VARCHAR,
            source       VARCHAR,
            issuing_body VARCHAR,
            doc_type     VARCHAR,
            doc_number   VARCHAR,
            published_at TIMESTAMP,
            available_at TIMESTAMP,
            headline     VARCHAR,
            summary      VARCHAR,
            body         VARCHAR,
            duplicate_of VARCHAR,
            fetched_at   TIMESTAMP
        );

        -- core.news (Unified News Schema): Lưu trữ toàn bộ 1.15M+ tin tức cổ phiếu, vĩ mô và tài chính
        CREATE TABLE IF NOT EXISTS core.news (
            source_url   VARCHAR NOT NULL PRIMARY KEY,
            news_type    VARCHAR NOT NULL,
            symbol       VARCHAR,
            source       VARCHAR NOT NULL,
            issuing_body VARCHAR,
            doc_type     VARCHAR,
            doc_number   VARCHAR,
            published_at TIMESTAMP NOT NULL,
            available_at TIMESTAMP NOT NULL,
            headline     VARCHAR NOT NULL,
            summary      VARCHAR,
            body         VARCHAR,
            duplicate_of VARCHAR,
            fetched_at   TIMESTAMP NOT NULL
        );

        -- Đảm bảo staging.news và core.news có đầy đủ các cột mở rộng trước khi tạo view
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS news_type VARCHAR;
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS issuing_body VARCHAR;
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS doc_type VARCHAR;
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS doc_number VARCHAR;
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS headline VARCHAR;
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS summary VARCHAR;
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS body VARCHAR;
        ALTER TABLE staging.news ADD COLUMN IF NOT EXISTS duplicate_of VARCHAR;

        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS news_type VARCHAR;
        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS issuing_body VARCHAR;
        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS doc_type VARCHAR;
        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS doc_number VARCHAR;
        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS headline VARCHAR;
        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS summary VARCHAR;
        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS body VARCHAR;
        ALTER TABLE core.news ADD COLUMN IF NOT EXISTS duplicate_of VARCHAR;

        -- Views tương thích ngược
        DROP VIEW IF EXISTS core.news_resources;
        DROP VIEW IF EXISTS core.macro_policy;
        CREATE OR REPLACE VIEW core.news_resources AS
        SELECT source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
        FROM core.news
        WHERE symbol IS NULL;

        CREATE OR REPLACE VIEW core.macro_policy AS
        SELECT source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
        FROM core.news
        WHERE news_type = 'MACRO_POLICY' OR (symbol IS NULL AND source IN ('baochinhphu', 'ssc', 'mof', 'sbv', 'gdt', 'moit', 'thoibaonganhang'));

        CREATE OR REPLACE VIEW core.v_stock_news AS
        SELECT * FROM core.news WHERE symbol IS NOT NULL;

        CREATE OR REPLACE VIEW core.v_macro_news AS
        SELECT * FROM core.news WHERE symbol IS NULL;

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

        CREATE TABLE IF NOT EXISTS staging.market_screener_snapshot (
            symbol                   VARCHAR NOT NULL,
            snapshot_date            DATE NOT NULL,
            exchange                 VARCHAR,
            price                    DOUBLE,
            reference_price          DOUBLE,
            ceiling_price            DOUBLE,
            floor_price              DOUBLE,
            price_change_percent     DOUBLE,
            market_cap               DOUBLE,
            accumulated_value        DOUBLE,
            accumulated_volume       DOUBLE,
            stock_strength           DOUBLE,
            data_json                VARCHAR,
            source                   VARCHAR NOT NULL DEFAULT 'VIETCAP_IQ_DIRECT',
            fetched_at               TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.market_screener_snapshot (
            symbol                   VARCHAR NOT NULL,
            snapshot_date            DATE NOT NULL,
            exchange                 VARCHAR,
            price                    DOUBLE,
            reference_price          DOUBLE,
            ceiling_price            DOUBLE,
            floor_price              DOUBLE,
            price_change_percent     DOUBLE,
            market_cap               DOUBLE,
            accumulated_value        DOUBLE,
            accumulated_volume       DOUBLE,
            stock_strength           DOUBLE,
            data_json                VARCHAR,
            source                   VARCHAR NOT NULL DEFAULT 'VIETCAP_IQ_DIRECT',
            fetched_at               TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, snapshot_date)
        );

        CREATE TABLE IF NOT EXISTS staging.index_valuation_series (
            index_code    VARCHAR NOT NULL,
            ratio_code    VARCHAR NOT NULL,
            report_date   DATE NOT NULL,
            ratio_value   DOUBLE NOT NULL,
            source        VARCHAR NOT NULL DEFAULT 'VNDIRECT_FINFO_DIRECT',
            fetched_at    TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.index_valuation_series (
            index_code    VARCHAR NOT NULL,
            ratio_code    VARCHAR NOT NULL,
            report_date   DATE NOT NULL,
            ratio_value   DOUBLE NOT NULL,
            source        VARCHAR NOT NULL DEFAULT 'VNDIRECT_FINFO_DIRECT',
            fetched_at    TIMESTAMP NOT NULL,
            PRIMARY KEY (index_code, ratio_code, report_date)
        );

        CREATE TABLE IF NOT EXISTS staging.market_breadth_series (
            exchange               VARCHAR NOT NULL,
            trade_date             DATE NOT NULL,
            pe                     DOUBLE,
            pb                     DOUBLE,
            above_ma20_pct         DOUBLE,
            above_ma50_pct         DOUBLE,
            above_ma200_pct        DOUBLE,
            avg_20d_above_ma50_pct DOUBLE,
            position_line          DOUBLE,
            close_index            DOUBLE,
            source                 VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
            fetched_at             TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.market_breadth_series (
            exchange               VARCHAR NOT NULL,
            trade_date             DATE NOT NULL,
            pe                     DOUBLE,
            pb                     DOUBLE,
            above_ma20_pct         DOUBLE,
            above_ma50_pct         DOUBLE,
            above_ma200_pct        DOUBLE,
            avg_20d_above_ma50_pct DOUBLE,
            position_line          DOUBLE,
            close_index            DOUBLE,
            source                 VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
            fetched_at             TIMESTAMP NOT NULL,
            PRIMARY KEY (exchange, trade_date)
        );

        CREATE TABLE IF NOT EXISTS staging.market_sentiment_snapshot (
            exchange           VARCHAR NOT NULL,
            snapshot_date      DATE NOT NULL,
            fear_greed_score   DOUBLE,
            advances           INTEGER,
            declines           INTEGER,
            no_change          INTEGER,
            mfi                DOUBLE,
            rsi                DOUBLE,
            index_change       DOUBLE,
            volume_change      DOUBLE,
            raw_json           VARCHAR,
            source             VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
            fetched_at         TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.market_sentiment_snapshot (
            exchange           VARCHAR NOT NULL,
            snapshot_date      DATE NOT NULL,
            fear_greed_score   DOUBLE,
            advances           INTEGER,
            declines           INTEGER,
            no_change          INTEGER,
            mfi                DOUBLE,
            rsi                DOUBLE,
            index_change       DOUBLE,
            volume_change      DOUBLE,
            raw_json           VARCHAR,
            source             VARCHAR NOT NULL DEFAULT 'ASEAN_SC_DIRECT',
            fetched_at         TIMESTAMP NOT NULL,
            PRIMARY KEY (exchange, snapshot_date)
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

        CREATE TABLE IF NOT EXISTS core.dim_sector (
            sector_id   INTEGER NOT NULL PRIMARY KEY,
            sector_name VARCHAR NOT NULL
        );

        CREATE TABLE IF NOT EXISTS core.dim_symbol_sector (
            symbol      VARCHAR NOT NULL,
            sector_id   INTEGER NOT NULL,
            PRIMARY KEY (symbol, sector_id)
        );

        CREATE TABLE IF NOT EXISTS core.sector_news_signal (
            source_url      VARCHAR NOT NULL,
            sector_id       INTEGER NOT NULL,
            sector_name     VARCHAR NOT NULL,
            matched_keyword VARCHAR NOT NULL,
            match_tier      VARCHAR NOT NULL,
            market_anchor   VARCHAR NOT NULL,
            fetched_at      TIMESTAMP NOT NULL,
            PRIMARY KEY (source_url, sector_id)
        );
        """
        schema_file = PROJECT_ROOT / "configs" / "duckdb_schema.sql"
        schema_sql = ""
        if schema_file.exists():
            try:
                schema_sql = schema_file.read_text(encoding="utf-8")
            except Exception:
                pass
        
        full_ddl = (schema_sql + "\n" + ddl) if schema_sql else ddl

        try:
            con = duckdb.connect(db_path, read_only=False)
            con.execute(full_ddl)
            con.close()
        except Exception as e:
            logger.debug("Không thể khởi tạo DDL trực tiếp trên %s: %s", db_path, e)
            # Khởi tạo trên buffer_db để dự phòng
            try:
                con_buf = duckdb.connect(self.buffer_db, read_only=False)
                con_buf.execute(full_ddl)
                con_buf.close()
            except Exception as e2:
                logger.warning("Không thể khởi tạo DDL trên buffer_db: %s", e2)

    def write_to_buffer(
        self,
        func: Callable[[duckdb.DuckDBPyConnection], Any],
    ) -> Any:
        """Ghi trực tiếp vào cơ sở dữ liệu đệm (buffer_db), hoàn toàn không chiếm khóa trên CSDL chính."""
        self._init_schemas(self.buffer_db)
        con_buf = duckdb.connect(self.buffer_db, read_only=False)
        try:
            return func(con_buf)
        finally:
            con_buf.close()

    def execute_with_retry(
        self,
        func: Callable[[duckdb.DuckDBPyConnection], Any],
        use_buffer_on_lock: bool = True,
    ) -> Any:
        """Thực thi một tác vụ cơ sở dữ liệu có kiểm soát khóa file và tự động dự phòng.
        Nếu buffer_first=True, ghi thẳng vào buffer_db với độ trễ tối thiểu và 0 rủi ro xung đột khóa.
        """
        if self.buffer_first:
            return self.write_to_buffer(func)

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
                        return self.write_to_buffer(func)
                raise

    def atomic_ingest_buffer(
        self,
        source_buffer_db: Optional[str] = None,
        target_db: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Thực hiện nạp nguyên tử (Atomic Ingestion) từ CSDL đệm sang CSDL chính qua giao dịch ACID.
        
        Quy trình chuẩn F000:
        1. Mở kết nối ghi vào target_db (giữ khóa cực ngắn, chỉ từ vài chục mili-giây).
        2. ATTACH buffer_db.
        3. Khởi tạo BEGIN TRANSACTION duy nhất.
        4. Tự động khớp các cột chung giữa target và buffer cho từng bảng có dữ liệu.
        5. INSERT OR REPLACE (hoặc INSERT OR IGNORE) và DELETE dữ liệu đệm đã nạp.
        6. COMMIT và DETACH.
        7. Giải phóng kết nối và nhả khóa ngay lập tức.
        """
        buf_path = pathlib.Path(source_buffer_db or self.buffer_db).resolve().as_posix()
        tgt_path = pathlib.Path(target_db or self.target_db).resolve().as_posix()

        if not os.path.exists(buf_path):
            return {"status": "SKIPPED", "reason": "Buffer file not found", "tables_synced": 0, "total_rows": 0, "elapsed_ms": 0.0}

        start_time = time.perf_counter()
        con_tgt = None

        for attempt in range(1, self.max_retries + 1):
            try:
                con_tgt = duckdb.connect(tgt_path, read_only=False)
                break
            except Exception as e:
                err_str = str(e)
                is_lock = "Cannot open file" in err_str or "being used by another process" in err_str
                if is_lock and attempt < self.max_retries:
                    logger.info(
                        "[Atomic Ingest %d/%d] %s đang bận, chờ %.1fs...",
                        attempt,
                        self.max_retries,
                        os.path.basename(tgt_path),
                        self.retry_delay * attempt,
                    )
                    time.sleep(self.retry_delay * attempt)
                else:
                    logger.warning("Không thể chiếm khóa ghi trên %s: %s", os.path.basename(tgt_path), e)
                    return {"status": "LOCKED", "error": str(e), "tables_synced": 0, "total_rows": 0, "elapsed_ms": 0.0}

        if con_tgt is None:
            return {"status": "FAILED", "tables_synced": 0, "total_rows": 0, "elapsed_ms": 0.0}

        # Bảng ưu tiên dùng INSERT OR REPLACE
        REPLACE_TABLES = {
            "market_ohlcv_daily", "market_ohlcv_1m", "fundamentals", "company_overview",
            "dim_symbol", "dim_symbol_cafef", "dim_symbol_sector", "dim_icb_hierarchy",
            "symbol_exchange_history", "financial_notes",
            "company_shareholders", "proprietary_flow", "market_foreign_flow_daily",
            "macro_rates", "realtime_quote_snapshot", "macro_economic_series",
            "market_screener_snapshot", "index_valuation_series", "market_breadth_series",
            "market_sentiment_snapshot"
        }

        try:
            # Gắn buffer_db ở chế độ READ_ONLY để tránh hoàn toàn xung đột khóa file
            con_tgt.execute(f"ATTACH '{buf_path}' AS buffer_db (READ_ONLY);")
            tbl_rows = con_tgt.execute("""
                SELECT schema_name, table_name 
                FROM duckdb_tables() 
                WHERE database_name = 'buffer_db' AND schema_name IN ('core', 'main', 'staging')
            """).fetchall()

            curr_db = con_tgt.execute("SELECT current_database()").fetchone()[0]

            # BẮT ĐẦU GIAO DỊCH NGUYÊN TỬ DUY NHẤT (ACID TRANSACTION) TRÊN CSDL ĐÍCH
            con_tgt.execute("BEGIN TRANSACTION;")

            total_synced_tables = 0
            total_synced_rows = 0
            details: Dict[str, int] = {}
            synced_cleanups = []

            for schema_name, tbl in tbl_rows:
                try:
                    # Kiểm tra số dòng thực tế trong buffer
                    row_cnt = con_tgt.execute(f"SELECT count(*) FROM buffer_db.{schema_name}.{tbl}").fetchone()[0]
                    if row_cnt == 0:
                        continue

                    # Xác định schema đích: ưu tiên giữ đúng schema của buffer nếu target có
                    if con_tgt.execute("""
                        SELECT count(*) 
                        FROM duckdb_tables() 
                        WHERE database_name = ? AND schema_name = ? AND table_name = ?
                    """, [curr_db, schema_name, tbl]).fetchone()[0] > 0:
                        target_schema = schema_name
                    elif con_tgt.execute("""
                        SELECT count(*) 
                        FROM duckdb_tables() 
                        WHERE database_name = ? AND schema_name = 'core' AND table_name = ?
                    """, [curr_db, tbl]).fetchone()[0] > 0:
                        target_schema = "core"
                    else:
                        continue

                    # Khớp cột động giữa target và buffer
                    cols_tgt = [r[1] for r in con_tgt.execute(f"PRAGMA table_info('{target_schema}.{tbl}')").fetchall()]
                    cols_buf = [r[1] for r in con_tgt.execute(f"PRAGMA table_info('buffer_db.{schema_name}.{tbl}')").fetchall()]
                    common_cols = [c for c in cols_tgt if c in cols_buf]

                    if common_cols:
                        cols_str = ", ".join(common_cols)
                        verb = "INSERT OR REPLACE" if tbl in REPLACE_TABLES else "INSERT OR IGNORE"
                        con_tgt.execute(f"""
                            {verb} INTO {target_schema}.{tbl} ({cols_str})
                            SELECT {cols_str} FROM buffer_db.{schema_name}.{tbl};
                        """)
                        synced_cleanups.append((schema_name, tbl))
                        total_synced_tables += 1
                        total_synced_rows += row_cnt
                        details[f"{target_schema}.{tbl}"] = row_cnt
                except Exception as ex_tbl:
                    logger.debug("Bỏ qua nạp bảng %s.%s: %s", schema_name, tbl, ex_tbl)

            # XÁC NHẬN TOÀN BỘ GIAO DỊCH TRÊN CSDL ĐÍCH
            con_tgt.execute("COMMIT;")
            try:
                con_tgt.execute("DETACH DATABASE IF EXISTS buffer_db;")
            except Exception:
                pass
            con_tgt.close()
            con_tgt = None

            # Dọn dẹp sạch các bản ghi đã nạp trong CSDL đệm (thực hiện riêng trên buffer_db để tuân thủ kiến trúc DuckDB)
            if synced_cleanups:
                try:
                    con_buf_clean = duckdb.connect(buf_path, read_only=False)
                    for s_name, t_name in synced_cleanups:
                        con_buf_clean.execute(f"DELETE FROM {s_name}.{t_name};")
                    con_buf_clean.close()
                except Exception as ex_clean:
                    logger.warning("Không thể xóa sạch dữ liệu đệm sau nạp: %s", ex_clean)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if total_synced_rows > 0:
                logger.info(
                    "⚡ [ATOMIC INGESTION THÀNH CÔNG] Đã nạp nguyên tử +%d dòng (%d bảng) vào %s trong %.2f ms!",
                    total_synced_rows,
                    total_synced_tables,
                    os.path.basename(tgt_path),
                    elapsed_ms,
                )
            return {
                "status": "SUCCESS",
                "tables_synced": total_synced_tables,
                "total_rows": total_synced_rows,
                "details": details,
                "elapsed_ms": elapsed_ms,
            }
        except Exception as e_tx:
            if con_tgt is not None:
                try:
                    con_tgt.execute("ROLLBACK;")
                except Exception:
                    pass
                try:
                    con_tgt.execute("DETACH DATABASE IF EXISTS buffer_db;")
                except Exception:
                    pass
            logger.error("💥 Lỗi Atomic Ingestion, đã ROLLBACK bảo vệ an toàn CSDL đích: %s", e_tx)
            return {
                "status": "FAILED",
                "error": str(e_tx),
                "tables_synced": 0,
                "total_rows": 0,
                "elapsed_ms": (time.perf_counter() - start_time) * 1000,
            }
        finally:
            if con_tgt is not None:
                try:
                    con_tgt.close()
                except Exception:
                    pass

    def sync_buffer_to_target(self) -> int:
        """Đồng bộ toàn bộ dữ liệu từ buffer_db vào target_db sử dụng Atomic Ingestion (tương thích ngược 100%)."""
        res = self.atomic_ingest_buffer()
        return res.get("tables_synced", 0)

    def sync_all_staging_databases(self, target_db: Optional[str] = None) -> Dict[str, Any]:
        """Quét và nạp nguyên tử tất cả các CSDL staging/buffer hiện có trong thư mục db/ vào CSDL đích."""
        tgt = target_db or self.target_db
        db_dir = os.path.dirname(tgt)
        staging_candidates = [
            os.path.join(db_dir, "vesta_crawled_fresh.duckdb"),
            os.path.join(db_dir, "staging_sync.duckdb"),
            os.path.join(db_dir, "vesta_news_staging.duckdb"),
        ]

        summary = {"total_rows": 0, "total_tables": 0, "details": {}}
        for s_db in staging_candidates:
            if os.path.exists(s_db) and os.path.abspath(s_db) != os.path.abspath(tgt):
                res = self.atomic_ingest_buffer(source_buffer_db=s_db, target_db=tgt)
                if res.get("status") == "SUCCESS":
                    summary["total_rows"] += res.get("total_rows", 0)
                    summary["total_tables"] += res.get("tables_synced", 0)
                    summary["details"][os.path.basename(s_db)] = res
        return summary


if __name__ == "__main__":
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="VESTA Atomic DuckDB Writer & Synchronization Hub")
    parser.add_argument("--target", default=DEFAULT_TARGET_DB, help="Đường dẫn file DuckDB đích (mặc định vesta_snapshot.duckdb)")
    parser.add_argument("--buffer", default=DEFAULT_BUFFER_DB, help="Đường dẫn file DuckDB đệm")
    parser.add_argument("--sync", action="store_true", help="Thực hiện Atomic Ingestion từ buffer_db sang target_db")
    parser.add_argument("--sync-all", action="store_true", help="Quét và nạp nguyên tử tất cả các database staging sang target_db")
    parser.add_argument("--status", action="store_true", help="Kiểm tra trạng thái các bảng trong buffer và target DB")

    args = parser.parse_args()
    writer = ResilientDuckDBWriter(target_db=args.target, buffer_db=args.buffer)

    if args.sync:
        print(f"\n[*] Đang thực hiện Atomic Ingestion từ {args.buffer} vào {args.target}...")
        res = writer.atomic_ingest_buffer()
        print(f"[+] Kết quả: Trạng thái={res.get('status')}, Bảng={res.get('tables_synced')}, Dòng={res.get('total_rows')}, Thời gian={res.get('elapsed_ms', 0):.2f}ms")
        if res.get("details"):
            for tbl, rows in res["details"].items():
                print(f"    • {tbl}: +{rows} dòng")

    elif args.sync_all:
        print(f"\n[*] Đang quét và nạp nguyên tử toàn bộ staging databases vào {args.target}...")
        res = writer.sync_all_staging_databases()
        print(f"[+] Tổng cộng nạp thành công: {res.get('total_rows'):,} dòng từ {res.get('total_tables')} bảng!")
        for s_name, s_res in res.get("details", {}).items():
            print(f"    • Nguồn {s_name}: {s_res.get('total_rows', 0):,} dòng trong {s_res.get('elapsed_ms', 0):.2f}ms")

    elif args.status or not (args.sync or args.sync_all):
        print(f"\n=== TRẠNG THÁI CSDL VESTA ===")
        print(f"Target DB: {writer.target_db} (Tồn tại: {os.path.exists(writer.target_db)})")
        print(f"Buffer DB: {writer.buffer_db} (Tồn tại: {os.path.exists(writer.buffer_db)})")
        if os.path.exists(writer.target_db):
            con = duckdb.connect(writer.target_db, read_only=True)
            tbl_cnt = con.execute("SELECT count(*) FROM duckdb_tables() WHERE schema_name IN ('core', 'staging')").fetchone()[0]
            print(f"Target Core Tables: {tbl_cnt} bảng.")
            con.close()

