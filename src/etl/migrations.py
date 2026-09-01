"""F009: DuckDB schema migrations.

DuckDB cannot ALTER a table's PRIMARY KEY in place. Any schema change that
touches a PRIMARY KEY (not just adding a nullable column) needs an
explicit migration: create the new-shaped table, copy existing data in,
drop the old table, rename. This module exists because item 3's
fundamentals PRIMARY KEY change would otherwise require dropping any
already-crawled data -- a real cost given multi-hour full-universe crawls
(see DECISIONS.md 2026-08-16).

Migrations are idempotent and safe to run against a fresh (never-crawled)
database too -- each one checks whether the old shape still exists before
doing anything.
"""
from __future__ import annotations

import sys
import pathlib

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402


def _table_has_column(con: duckdb.DuckDBPyConnection, schema: str, table: str, column: str) -> bool:
    row = con.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = ? AND table_name = ? AND column_name = ?",
        [schema, table, column],
    ).fetchone()
    return bool(row and row[0] > 0)


def _primary_key_columns(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> list[str]:
    rows = con.execute(
        """
        SELECT column_name FROM (
            SELECT constraint_column_names AS ccn
            FROM duckdb_constraints()
            WHERE schema_name = ? AND table_name = ? AND constraint_type = 'PRIMARY KEY'
        ), UNNEST(ccn) AS t(column_name)
        """,
        [schema, table],
    ).fetchall()
    return [r[0] for r in rows]


def migrate_fundamentals_append_only_pk(con: duckdb.DuckDBPyConnection) -> bool:
    """Item 3: core.fundamentals PRIMARY KEY (symbol, report_type,
    period_end) -> (symbol, report_type, period_end, fetched_at).
    Preserves all existing rows. Returns True if a migration actually ran,
    False if the table was already in the new shape (or didn't exist yet
    -- bootstrap_schema() will create it correctly from scratch).
    """
    exists_row = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'core' AND table_name = 'fundamentals'"
    ).fetchone()
    exists_count = exists_row[0] if exists_row is not None else 0
    if exists_count == 0:
        return False  # nothing to migrate -- bootstrap_schema() handles fresh creation

    pk_cols = _primary_key_columns(con, "core", "fundamentals")
    if "fetched_at" in pk_cols:
        return False  # already migrated

    con.execute(
        """
        CREATE TABLE core.fundamentals_migrated (
            symbol       VARCHAR NOT NULL,
            report_type  VARCHAR NOT NULL,
            period_end   DATE NOT NULL,
            available_at DATE NOT NULL,
            data_json    VARCHAR NOT NULL,
            fetched_at   TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, report_type, period_end, fetched_at)
        )
        """
    )
    con.execute("INSERT INTO core.fundamentals_migrated SELECT * FROM core.fundamentals")
    before_row = con.execute("SELECT COUNT(*) FROM core.fundamentals").fetchone()
    after_row = con.execute("SELECT COUNT(*) FROM core.fundamentals_migrated").fetchone()
    row_count_before = before_row[0] if before_row is not None else 0
    row_count_after = after_row[0] if after_row is not None else 0
    if row_count_before != row_count_after:
        con.execute("DROP TABLE core.fundamentals_migrated")
        raise RuntimeError(
            f"Migration aborted: row count mismatch (before={row_count_before}, "
            f"after={row_count_after}). Old table left untouched -- investigate "
            f"before retrying."
        )

    con.execute("DROP TABLE core.fundamentals")
    con.execute("ALTER TABLE core.fundamentals_migrated RENAME TO fundamentals")
    print(f"[migration] core.fundamentals: migrated {row_count_after} row(s) to the new PRIMARY KEY, no data lost")
    return True


def migrate_news_add_duplicate_of_column(con: duckdb.DuckDBPyConnection) -> bool:
    """Item 5: adds a nullable duplicate_of column to core.news/
    staging.news. This is additive (no PRIMARY KEY change), so a plain
    ALTER TABLE ADD COLUMN is sufficient -- no copy/drop/rename needed.
    """
    ran_any = False
    for schema in ("staging", "news"), ("core", "news"):
        table_schema, table_name = schema
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = ?",
            [table_schema, table_name],
        ).fetchone()
        exists_count = exists[0] if exists is not None else 0
        if exists_count == 0:
            continue
        if _table_has_column(con, table_schema, table_name, "duplicate_of"):
            continue
        con.execute(f"ALTER TABLE {table_schema}.{table_name} ADD COLUMN duplicate_of VARCHAR")
        print(f"[migration] {table_schema}.{table_name}: added duplicate_of column")
        ran_any = True
    return ran_any


def migrate_dim_symbol_add_is_delisted_column(con: duckdb.DuckDBPyConnection) -> bool:
    """F001 delisted fix: adds a nullable is_delisted column to core.dim_symbol."""
    exists = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'core' AND table_name = 'dim_symbol'"
    ).fetchone()
    exists_count = exists[0] if exists is not None else 0
    if exists_count == 0:
        return False
    if _table_has_column(con, "core", "dim_symbol", "is_delisted"):
        return False
    con.execute("ALTER TABLE core.dim_symbol ADD COLUMN is_delisted BOOLEAN")
    print("[migration] core.dim_symbol: added is_delisted column")
    return True


def run_all_migrations(con: "duckdb.DuckDBPyConnection | None" = None) -> duckdb.DuckDBPyConnection:
    """Entry point: run every migration in order. Safe to call every time
    init.sh runs -- each migration is idempotent and a no-op if already
    applied or if the table doesn't exist yet (bootstrap_schema handles
    fresh creation in the new shape directly).
    """
    con = con or db.bootstrap_schema()
    migrate_fundamentals_append_only_pk(con)
    migrate_news_add_duplicate_of_column(con)
    migrate_dim_symbol_add_is_delisted_column(con)
    return con


if __name__ == "__main__":
    run_all_migrations()
    print("[migration] all migrations checked/applied")