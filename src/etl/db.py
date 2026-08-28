"""DuckDB connection + schema bootstrap for VESTA (F000).

Every crawler/pipeline module should get its connection via `connect()`
rather than opening duckdb.connect() directly, so the DB path stays in one
place and schema bootstrap is guaranteed to have run.
"""
from __future__ import annotations

import os
import pathlib

import duckdb

# Single source of truth for the DB location. db/ is gitignored (see
# conventions.md "data/ and out/... are gitignored" pattern extended to db/).
DB_PATH = pathlib.Path(__file__).resolve().parents[2] / "db" / "vesta.duckdb"
SCHEMA_SQL_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "configs" / "duckdb_schema.sql"
)

REQUIRED_SCHEMAS = ("staging", "core", "meta")


def load_env() -> None:
    """Load environment variables from .env if not already set."""
    env_path = pathlib.Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k_str = k.strip()
                    if k_str not in os.environ:
                        os.environ[k_str] = v.strip().strip("'\"")


def connect(db_path: pathlib.Path | str = DB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a connection to the VESTA DuckDB database.

    Does not bootstrap schema — call `bootstrap_schema()` explicitly (init.sh
    does this once at install time) so a normal `connect()` call in a
    crawler stays cheap and side-effect-free.
    """
    db_path = pathlib.Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path), read_only=read_only)


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