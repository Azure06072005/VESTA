"""F000 verification: schema bootstrap creates staging, core, meta,
and meta.crawl_progress with the expected columns. Uses a temp DB path
so this test never touches the real db/vesta.duckdb.
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db  # noqa: E402


def test_bootstrap_creates_three_schemas(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    schemas = db.verify_schemas(con)
    assert schemas == ["core", "meta", "staging"]


def test_crawl_progress_table_exists_with_expected_columns(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    cols = con.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'meta' AND table_name = 'crawl_progress' "
        "ORDER BY ordinal_position"
    ).fetchall()
    col_names = [c[0] for c in cols]
    assert col_names == [
        "dataset_name",
        "symbol",
        "status",
        "retry_count",
        "last_attempt",
    ]


def test_bootstrap_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    db.bootstrap_schema(db_path)
    # Re-run against the same DB file — must not raise.
    con2 = db.bootstrap_schema(db_path)
    assert db.verify_schemas(con2) == ["core", "meta", "staging"]