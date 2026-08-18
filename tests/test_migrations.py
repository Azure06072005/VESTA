"""Migration verification.

The critical property under test: migrate_fundamentals_append_only_pk
must never lose a row when migrating a pre-existing (old-shape) database,
and must correctly no-op when the database is already in the new shape
(e.g. freshly bootstrapped via the updated duckdb_schema.sql).
"""
from __future__ import annotations

import sys
import pathlib

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402
from etl import migrations  # noqa: E402


def _old_shape_db(db_path: pathlib.Path) -> duckdb.DuckDBPyConnection:
    """Simulates a database created BEFORE the item 3 schema fix -- old
    3-column PRIMARY KEY, some real data already in it.
    """
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS core")
    con.execute("CREATE SCHEMA IF NOT EXISTS staging")
    con.execute(
        """CREATE TABLE core.fundamentals (
            symbol VARCHAR, report_type VARCHAR, period_end DATE,
            available_at DATE, data_json VARCHAR, fetched_at TIMESTAMP,
            PRIMARY KEY (symbol, report_type, period_end)
        )"""
    )
    con.execute(
        "INSERT INTO core.fundamentals VALUES "
        "('FPT','income_statement','2026-01-01','2026-01-31','{\"revenue\":100}','2026-01-01 00:00:00'), "
        "('VNM','ratio','2026-01-01','2026-01-31','{\"pe\":15}','2026-01-01 00:00:00')"
    )
    return con


def test_migrate_fundamentals_preserves_existing_rows_exactly(tmp_path):
    con = _old_shape_db(tmp_path / "old.duckdb")
    before = set(con.execute("SELECT * FROM core.fundamentals").fetchall())

    ran = migrations.migrate_fundamentals_append_only_pk(con)
    assert ran is True

    after = set(con.execute("SELECT * FROM core.fundamentals").fetchall())
    assert before == after  # byte-for-byte identical, nothing lost or altered


def test_migrate_fundamentals_updates_primary_key(tmp_path):
    con = _old_shape_db(tmp_path / "old.duckdb")
    migrations.migrate_fundamentals_append_only_pk(con)

    pk_cols = migrations._primary_key_columns(con, "core", "fundamentals")
    assert "fetched_at" in pk_cols


def test_migrate_fundamentals_allows_revision_after_migration(tmp_path):
    con = _old_shape_db(tmp_path / "old.duckdb")
    migrations.migrate_fundamentals_append_only_pk(con)

    # Under the OLD PK this second insert would violate the constraint
    # (same symbol/report_type/period_end). Under the NEW PK it succeeds
    # because fetched_at differs -- this is the whole point of the fix.
    con.execute(
        "INSERT INTO core.fundamentals VALUES "
        "('FPT','income_statement','2026-01-01','2026-01-31','{\"revenue\":999}','2026-02-01 00:00:00')"
    )
    row_count = con.execute(
        "SELECT COUNT(*) FROM core.fundamentals WHERE symbol='FPT' AND report_type='income_statement'"
    ).fetchone()[0]
    assert row_count == 2


def test_migrate_fundamentals_is_a_noop_on_already_new_shape(tmp_path):
    db_path = tmp_path / "fresh.duckdb"
    con = db.bootstrap_schema(db_path)  # already built with the new PK
    ran = migrations.migrate_fundamentals_append_only_pk(con)
    assert ran is False


def test_migrate_fundamentals_is_a_noop_when_table_does_not_exist(tmp_path):
    con = duckdb.connect(str(tmp_path / "empty.duckdb"))
    con.execute("CREATE SCHEMA IF NOT EXISTS core")
    ran = migrations.migrate_fundamentals_append_only_pk(con)
    assert ran is False


def test_migrate_fundamentals_row_count_guard_exists_in_source():
    # The row-count-mismatch abort guard in migrate_fundamentals_append_
    # only_pk can't be fault-injected against DuckDB's C-extension
    # connection object (its methods are read-only, monkeypatch can't
    # intercept them) -- verified by direct source inspection instead:
    # the function must compare before/after counts and raise before
    # dropping the original table if they differ.
    import inspect

    source = inspect.getsource(migrations.migrate_fundamentals_append_only_pk)
    assert "row_count_before" in source
    assert "row_count_after" in source
    assert "raise RuntimeError" in source
    # The destructive DROP TABLE core.fundamentals (the original, not the
    # _migrated staging copy) must appear AFTER the raise in source order.
    destructive_drop = 'con.execute("DROP TABLE core.fundamentals")'
    assert destructive_drop in source
    assert source.index("raise RuntimeError") < source.index(destructive_drop)


def test_migrate_news_add_duplicate_of_column_is_additive_and_idempotent(tmp_path):
    db_path = tmp_path / "test.duckdb"
    con = db.bootstrap_schema(db_path)

    ran1 = migrations.migrate_news_add_duplicate_of_column(con)
    assert ran1 is True
    cols = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='core' AND table_name='news'"
        ).fetchall()
    }
    assert "duplicate_of" in cols

    ran2 = migrations.migrate_news_add_duplicate_of_column(con)
    assert ran2 is False  # already added -- correctly detected, not re-run


def test_run_all_migrations_is_safe_on_a_completely_fresh_database(tmp_path):
    db_path = tmp_path / "brand_new.duckdb"
    con = migrations.run_all_migrations(db.bootstrap_schema(db_path))
    # Should not raise, and the DB should be fully usable afterward.
    con.execute("SELECT * FROM core.fundamentals").fetchall()
    con.execute("SELECT * FROM core.news").fetchall()