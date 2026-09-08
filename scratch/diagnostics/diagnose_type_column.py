"""Before writing any fix to build_dim_symbol(), check what the unused
'type' column (confirmed present in the schema docstring since 2026-08-11,
but never consumed by build_dim_symbol()) actually contains -- this is
likely the correct, real discriminator between equities and bonds, rather
than guessing from exchange==NULL or symbol string patterns.

Usage:
    ./.venv/bin/python scratch/diagnose_type_column.py --db db/vesta.duckdb
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from crawlers import dim_symbol  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    print("=== FRESH fetch_raw() -- what does 'type' actually contain today? ===")
    exchange_df, _industry_df = dim_symbol.fetch_raw()
    print("Columns:", list(exchange_df.columns))
    if "type" in exchange_df.columns:
        print("\n'type' value counts:")
        print(exchange_df["type"].value_counts(dropna=False).to_string())
        print("\n'exchange' x 'type' cross-tab:")
        print(exchange_df.groupby(["exchange", "type"], dropna=False).size().to_string())
    else:
        print("NO 'type' column in the fresh response -- docstring is stale, "
              "the schema itself has changed since 2026-08-11.")

    print("\n=== BBC / BCG real row, all columns ===")
    print(exchange_df[exchange_df["symbol"].isin(["BBC", "BCG"])].to_string())

    print("\n=== Sample of a real bond-looking stored symbol, if type-fetchable ===")
    con = duckdb.connect(args.db, read_only=True)
    bond_symbols = [
        r[0] for r in con.execute(
            "SELECT symbol FROM core.dim_symbol WHERE exchange IS NULL LIMIT 5"
        ).fetchall()
    ]
    print("Stored bond-suspect symbols:", bond_symbols)
    if "type" in exchange_df.columns:
        match = exchange_df[exchange_df["symbol"].isin(bond_symbols)]
        print("Do any of these appear in today's fresh response?")
        print(match.to_string() if len(match) else "(none -- today's narrower response excludes them entirely)")
    con.close()


if __name__ == "__main__":
    main()
