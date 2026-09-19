"""src/etl/sync_enrichment_data.py

Sync script to promote freshly crawled data (proprietary flow, financial notes, macro rates)
from db/test_db/vesta_test.duckdb to main db/vesta.duckdb once write access is available.
"""
from pathlib import Path
import logging
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_enrichment")

def sync_data(src_path: str = "db/test_db/vesta_test.duckdb", dst_path: str = "db/vesta.duckdb"):
    logger.info(f"Checking sync from {src_path} to {dst_path}...")
    try:
        con_dst = duckdb.connect(dst_path, read_only=False)
    except Exception as e:
        logger.error(f"Cannot open destination DB {dst_path} in write mode: {e}")
        return False

    try:
        con_dst.execute(f"ATTACH '{src_path}' AS src_db (READ_ONLY);")

        # 1. Sync proprietary_flow
        con_dst.execute("""
            CREATE SCHEMA IF NOT EXISTS core;
            CREATE TABLE IF NOT EXISTS core.proprietary_flow (
                symbol VARCHAR NOT NULL,
                date DATE NOT NULL,
                buy_vol DOUBLE,
                buy_val DOUBLE,
                sell_vol DOUBLE,
                sell_val DOUBLE,
                net_vol DOUBLE,
                net_val DOUBLE,
                fetched_at TIMESTAMP NOT NULL,
                PRIMARY KEY (symbol, date)
            );
            INSERT INTO core.proprietary_flow
            SELECT * FROM src_db.core.proprietary_flow
            ON CONFLICT (symbol, date) DO NOTHING;
        """)
        c_prop = con_dst.execute("SELECT count(*) FROM core.proprietary_flow").fetchone()[0]
        logger.info(f" -> core.proprietary_flow sync complete: {c_prop} rows total.")

        # 2. Sync financial_notes
        con_dst.execute("""
            CREATE TABLE IF NOT EXISTS core.financial_notes (
                symbol VARCHAR NOT NULL,
                period VARCHAR NOT NULL,
                note_id VARCHAR NOT NULL,
                note_name VARCHAR,
                item_order INTEGER,
                item_level INTEGER,
                unit VARCHAR,
                value DOUBLE,
                fetched_at TIMESTAMP NOT NULL,
                PRIMARY KEY (symbol, period, note_id)
            );
            INSERT INTO core.financial_notes
            SELECT * FROM src_db.core.financial_notes
            ON CONFLICT (symbol, period, note_id) DO NOTHING;
        """)
        c_notes = con_dst.execute("SELECT count(*) FROM core.financial_notes").fetchone()[0]
        logger.info(f" -> core.financial_notes sync complete: {c_notes} rows total.")

        # 3. Sync macro_rates
        con_dst.execute("""
            CREATE TABLE IF NOT EXISTS core.macro_rates (
                rate_type VARCHAR NOT NULL,
                term VARCHAR NOT NULL,
                date DATE NOT NULL,
                rate_value DOUBLE NOT NULL,
                source VARCHAR NOT NULL,
                fetched_at TIMESTAMP NOT NULL,
                PRIMARY KEY (rate_type, term, date)
            );
            INSERT INTO core.macro_rates
            SELECT * FROM src_db.core.macro_rates
            ON CONFLICT (rate_type, term, date) DO NOTHING;
        """)
        c_rates = con_dst.execute("SELECT count(*) FROM core.macro_rates").fetchone()[0]
        logger.info(f" -> core.macro_rates sync complete: {c_rates} rows total.")

        return True
    finally:
        con_dst.close()

if __name__ == "__main__":
    sync_data()
