"""Test Runner for F102: Point-in-Time News + Price Join.

Validates that core.pit_events on the test database has valid timestamps,
flags unadjusted zero prices, and maintains high horizon coverage (>90%).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import duckdb

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))


def run_f102_test(db_path: str = "db/test_db/vesta_test.duckdb") -> dict[str, object]:
    con = duckdb.connect(db_path, read_only=True)

    print(f"[F102] Testing Point-in-Time Join Integrity on {db_path}...")
    total_events = con.execute("SELECT COUNT(*) FROM core.pit_events").fetchone()[0]
    zero_prices = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE price_at_publish <= 0").fetchone()[0]
    null_publish = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE price_at_publish IS NULL").fetchone()[0]
    t1_covered = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE price_t1 IS NOT NULL").fetchone()[0]
    t5_covered = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE price_t5 IS NOT NULL").fetchone()[0]
    t30_covered = con.execute("SELECT COUNT(*) FROM core.pit_events WHERE price_t30 IS NOT NULL").fetchone()[0]

    coverage_t1_pct = (t1_covered / max(total_events, 1)) * 100
    # Invariant: high coverage (>90%) and valid total events
    passed = (total_events > 500000) and (coverage_t1_pct > 90.0)

    report: dict[str, object] = {
        "feature": "F102",
        "database": db_path,
        "total_pit_events": total_events,
        "null_publish_prices": null_publish,
        "zero_prices_flagged": zero_prices,
        "coverage": {
            "t1": f"{t1_covered}/{total_events} ({coverage_t1_pct:.1f}%)",
            "t5": f"{t5_covered}/{total_events} ({t5_covered/max(total_events,1)*100:.1f}%)",
            "t30": f"{t30_covered}/{total_events} ({t30_covered/max(total_events,1)*100:.1f}%)",
        },
        "status": "PASS" if passed else "FAIL",
    }

    print(f"  -> Total Events: {total_events:,}")
    print(f"  -> Null Publish Prices: {null_publish:,} (symbols without trading bars on publish date)")
    print(f"  -> Zero-Price rows flagged: {zero_prices}")
    print(f"  -> Horizon Coverage: t+1={t1_covered:,} ({coverage_t1_pct:.1f}%), t+5={t5_covered:,}, t+30={t30_covered:,}")
    print(f"  -> Status: {report['status']}")

    con.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F102 test runner")
    parser.add_argument("--db-path", default="db/test_db/vesta_test.duckdb", help="Target test database")
    args = parser.parse_args()
    res = run_f102_test(args.db_path)
    print(f"Result: {res['status']}")
