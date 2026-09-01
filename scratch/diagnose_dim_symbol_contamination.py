"""Follow-up diagnostic for the core.dim_symbol contamination found
2026-08-31: 1,469 NULL-exchange rows (bonds) and 14 unexplained 'XHNF'
rows alongside the expected HOSE/HNX/UPCOM counts.

Question: are these contaminated rows time-isolated (a single stale write
from a different vnstock_data version, never cleaned up because a later
dim_symbol.run() somehow didn't fully overwrite them), or interleaved with
the legitimate rows (which would suggest something bypassed
write_dim_symbol()'s DELETE+INSERT entirely, a more serious integrity
concern)?

Usage:
    ./.venv/bin/python scratch/diagnose_dim_symbol_contamination.py --db db/vesta.duckdb
"""
from __future__ import annotations

import argparse

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    con = duckdb.connect(args.db, read_only=True)

    print("--- fetched_at distribution by exchange bucket ---")
    rows = con.execute(
        """
        SELECT
            CASE WHEN exchange IS NULL THEN 'NULL (suspected bonds)'
                 ELSE exchange END AS exchange_bucket,
            MIN(fetched_at) AS earliest,
            MAX(fetched_at) AS latest,
            COUNT(*) AS n
        FROM core.dim_symbol
        GROUP BY exchange_bucket
        ORDER BY n DESC
        """
    ).fetchall()
    for exchange_bucket, earliest, latest, n in rows:
        print(f"{exchange_bucket:25s}  n={n:5d}  fetched_at range: {earliest} .. {latest}")

    print("\n--- distinct fetched_at timestamps overall (if this is >1, ")
    print("    write_dim_symbol()'s DELETE+INSERT was NOT the only writer) ---")
    distinct_ts = con.execute(
        "SELECT DISTINCT fetched_at FROM core.dim_symbol ORDER BY fetched_at"
    ).fetchall()
    for (ts,) in distinct_ts:
        n = con.execute(
            "SELECT COUNT(*) FROM core.dim_symbol WHERE fetched_at = ?", [ts]
        ).fetchone()[0]
        print(f"  {ts}  -> {n} rows")

    print("\n--- sample of the 14 unexplained 'XHNF' rows ---")
    xhnf = con.execute(
        "SELECT symbol, organ_name, exchange, fetched_at FROM core.dim_symbol "
        "WHERE exchange = 'XHNF' LIMIT 14"
    ).fetchall()
    for r in xhnf:
        print(" ", r)

    print(
        "\nInterpretation:\n"
        "  - ONE distinct fetched_at overall: all 3,418 rows came from a single "
        "write_dim_symbol() call -- meaning that ONE historical run of "
        "vnstock_data (whatever version was installed then) really did return "
        "bonds+XHNF+everything in a single list_by_exchange() response, and the "
        "version currently installed (3.2.2) returns a narrower, cleaner set. "
        "This points to vnstock_data version drift changing the API's own "
        "response shape over time, not a code bug in this repo.\n"
        "  - MULTIPLE distinct fetched_at values: something wrote to "
        "core.dim_symbol outside of a single dim_symbol.run() call -- worth "
        "grepping the codebase for any direct INSERT INTO core.dim_symbol "
        "that isn't in write_dim_symbol()."
    )

    con.close()


if __name__ == "__main__":
    main()
