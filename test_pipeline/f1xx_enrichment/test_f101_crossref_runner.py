"""Test Runner for F101: Cross-Dataset Referential Integrity.

Validates that every symbol in core tables exists in core.dim_symbol and
no future timestamps exist on the target test database (db/vesta_test.duckdb).
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys
import duckdb

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from pipeline.f1xx_enrichment.validate_crossref import (
    TABLES_WITH_SYMBOL,
    find_future_timestamps,
    find_orphan_symbols,
    get_valid_symbols,
)


def run_f101_test(db_path: str = "db/vesta_test.duckdb") -> dict[str, object]:
    con = duckdb.connect(db_path, read_only=True)
    valid_symbols = get_valid_symbols(con)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    report: dict[str, object] = {
        "feature": "F101",
        "database": db_path,
        "valid_symbols_count": len(valid_symbols),
        "tables_checked": {},
        "status": "PASS",
    }

    print(f"[F101] Testing Cross-Dataset Referential Integrity on {db_path}...")
    all_clean = True

    for schema, table, symbol_col, ts_col in TABLES_WITH_SYMBOL:
        # Check table presence
        table_exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchone()[0] > 0

        if not table_exists:
            continue

        orphans = find_orphan_symbols(con, schema, table, symbol_col, valid_symbols)
        future_count = find_future_timestamps(con, schema, table, ts_col, now=now)
        passed = (len(orphans) == 0) and (future_count == 0)
        if not passed:
            all_clean = False

        report["tables_checked"][f"{schema}.{table}"] = {
            "orphan_symbols": orphans,
            "future_timestamps": future_count,
            "passed": passed,
        }
        status_str = "OK" if passed else f"FAIL (orphans={len(orphans)}, future={future_count})"
        print(f"  -> {schema}.{table}: {status_str}")

    report["status"] = "PASS" if all_clean else "FAIL"
    con.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F101 test runner")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    args = parser.parse_args()
    res = run_f101_test(args.db_path)
    print(f"Result: {res['status']}")
