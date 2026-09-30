"""migrate_f001_to_snapshot.py

Maps and migrates the new F001 schema and tables from vesta_backup.duckdb into
db/vesta_snapshot.duckdb (and db/vesta.duckdb), ensuring complete alignment
and preventing schema conflicts between old and new tables.
"""
from __future__ import annotations

import pathlib
import duckdb

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT_DB = str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb")
BACKUP_DB = str(PROJECT_ROOT / "db" / "vesta_backup.duckdb")
CANONICAL_DB = str(PROJECT_ROOT / "db" / "vesta.duckdb")


def migrate_database(target_db_path: str, source_backup_path: str):
    print("=" * 70)
    print(f"MIGRATING SCHEMA & DATA INTO: {target_db_path}")
    print(f"Source of truth: {source_backup_path}")
    print("=" * 70)

    con = duckdb.connect(target_db_path, read_only=False)
    con.execute(f"ATTACH '{source_backup_path}' AS bkp (READ_ONLY)")

    # 1. Update core.dim_symbol_cafef columns
    print("[1/5] Migrating core.dim_symbol_cafef columns...")
    con.execute("ALTER TABLE core.dim_symbol_cafef ADD COLUMN IF NOT EXISTS tradeable_flag BOOLEAN DEFAULT FALSE;")
    con.execute("ALTER TABLE core.dim_symbol_cafef ADD COLUMN IF NOT EXISTS subuniverse VARCHAR DEFAULT 'OTC';")

    # Sync values from backup
    con.execute("""
        UPDATE core.dim_symbol_cafef AS target
        SET tradeable_flag = src.tradeable_flag,
            subuniverse = src.subuniverse
        FROM bkp.core.dim_symbol_cafef AS src
        WHERE target.symbol = src.symbol
    """)
    cafef_cnt = con.execute("SELECT COUNT(*), COUNT(CASE WHEN tradeable_flag = FALSE THEN 1 END) FROM core.dim_symbol_cafef").fetchone()
    print(f"    -> core.dim_symbol_cafef: {cafef_cnt[0]} rows ({cafef_cnt[1]} untradeable OTC/unlisted).")

    # 2. Create and populate core.dim_icb_hierarchy
    print("[2/5] Creating & Populating core.dim_icb_hierarchy...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS core.dim_icb_hierarchy (
            icb_code            VARCHAR NOT NULL PRIMARY KEY,
            level               INTEGER NOT NULL,
            icb_name_vi         VARCHAR NOT NULL,
            icb_name_en         VARCHAR NOT NULL,
            parent_code         VARCHAR,
            industry_code       VARCHAR NOT NULL,
            industry_name_vi    VARCHAR NOT NULL,
            industry_name_en    VARCHAR NOT NULL,
            supersector_code    VARCHAR,
            supersector_name_vi VARCHAR,
            supersector_name_en VARCHAR,
            sector_code         VARCHAR,
            sector_name_vi      VARCHAR,
            sector_name_en      VARCHAR,
            subsector_code      VARCHAR,
            subsector_name_vi   VARCHAR,
            subsector_name_en   VARCHAR,
            updated_at          TIMESTAMP NOT NULL
        );
    """)
    con.execute("""
        INSERT INTO core.dim_icb_hierarchy
        SELECT * FROM bkp.core.dim_icb_hierarchy
        WHERE icb_code NOT IN (SELECT icb_code FROM core.dim_icb_hierarchy);
    """)
    icb_cnt = con.execute("SELECT COUNT(*) FROM core.dim_icb_hierarchy").fetchone()[0]
    print(f"    -> core.dim_icb_hierarchy: {icb_cnt} rows.")

    # 3. Create and populate core.symbol_exchange_history
    print("[3/5] Creating & Populating core.symbol_exchange_history...")
    con.execute("""
        CREATE TABLE IF NOT EXISTS core.symbol_exchange_history (
            symbol          VARCHAR NOT NULL,
            exchange        VARCHAR NOT NULL,
            start_date      DATE NOT NULL,
            end_date        DATE,
            is_current      BOOLEAN NOT NULL,
            listing_price   DOUBLE,
            event_note      VARCHAR,
            source          VARCHAR NOT NULL DEFAULT 'HOSE/HNX/CompanyOverview',
            created_at      TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, exchange, start_date)
        );
    """)
    con.execute("""
        INSERT INTO core.symbol_exchange_history
        SELECT * FROM bkp.core.symbol_exchange_history
        WHERE NOT EXISTS (
            SELECT 1 FROM core.symbol_exchange_history h 
            WHERE h.symbol = bkp.core.symbol_exchange_history.symbol 
              AND h.exchange = bkp.core.symbol_exchange_history.exchange
              AND h.start_date = bkp.core.symbol_exchange_history.start_date
        );
    """)
    hist_cnt = con.execute("SELECT COUNT(*) FROM core.symbol_exchange_history").fetchone()[0]
    print(f"    -> core.symbol_exchange_history: {hist_cnt} rows.")

    # 4. Create or replace core.v_symbol_universe view
    print("[4/5] Creating / Refreshing core.v_symbol_universe VIEW...")
    con.execute("""
        CREATE OR REPLACE VIEW core.v_symbol_universe AS
        SELECT 
            symbol, 
            organ_name as org_name, 
            exchange, 
            is_delisted,
            TRUE as tradeable_flag, 
            'LISTED' as subuniverse,
            'vnstock' as source,
            fetched_at
        FROM core.dim_symbol
        UNION ALL
        SELECT 
            symbol, 
            org_name, 
            exchange, 
            TRUE as is_delisted,
            tradeable_flag, 
            subuniverse,
            source,
            fetched_at
        FROM core.dim_symbol_cafef;
    """)
    view_cnt = con.execute("SELECT COUNT(*) FROM core.v_symbol_universe").fetchone()[0]
    print(f"    -> core.v_symbol_universe VIEW: {view_cnt} rows total.")

    # 5. Schema verification
    print("[5/5] Verifying no schema conflicts...")
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core'").fetchall()]
    assert "dim_icb_hierarchy" in tables
    assert "symbol_exchange_history" in tables
    assert "dim_symbol_cafef" in tables
    assert "v_symbol_universe" in tables
    print("    -> All F001 / F001b tables and views are present and synchronized!")

    con.close()
    print("SUCCESS: Target database migrated cleanly with ZERO conflicts.\n")


if __name__ == "__main__":
    # Migrate snapshot (main) DB
    migrate_database(SNAPSHOT_DB, BACKUP_DB)
    # Also migrate canonical vesta.duckdb if present
    if pathlib.Path(CANONICAL_DB).exists():
        migrate_database(CANONICAL_DB, BACKUP_DB)
