"""DuckDB connection + schema bootstrap for VESTA (F000).

Every crawler/pipeline module should get its connection via `connect()`
rather than opening duckdb.connect() directly, so the DB path stays in one
place and schema bootstrap is guaranteed to have run.
"""
from __future__ import annotations

import pathlib

import duckdb

# Single source of truth for the DB location. db/ is gitignored (see
# conventions.md "data/ and out/... are gitignored" pattern extended to db/).
DB_PATH = pathlib.Path(__file__).resolve().parents[2] / "db" / "vesta.duckdb"
SCHEMA_SQL_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "configs" / "duckdb_schema.sql"
)

REQUIRED_SCHEMAS = ("staging", "core", "meta")


def connect(db_path: pathlib.Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Open a connection to the VESTA DuckDB database.

    Does not bootstrap schema — call `bootstrap_schema()` explicitly (init.sh
    does this once at install time) so a normal `connect()` call in a
    crawler stays cheap and side-effect-free.
    """
    db_path = pathlib.Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def bootstrap_schema(db_path: pathlib.Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Create staging/core/meta schemas and meta.crawl_progress if missing.

    Idempotent: safe to call against an already-bootstrapped database.
    """
    con = connect(db_path)
    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    con.execute(sql)
    return con


def verify_schemas(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Return the sorted list of user-created schema names present."""
    rows = con.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name IN ('staging', 'core', 'meta')"
    ).fetchall()
    return sorted(r[0] for r in rows)


if __name__ == "__main__":
    connection = bootstrap_schema()
    found = verify_schemas(connection)
    missing = [s for s in REQUIRED_SCHEMAS if s not in found]
    if missing:
        raise SystemExit(f"F000 bootstrap incomplete, missing schemas: {missing}")
    print(f"F000 OK — schemas present: {found}")