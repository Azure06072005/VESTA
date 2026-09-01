"""F001b live integration: cross-reference cafef.vn directory against the
REAL core.dim_symbol table and (optionally) write results.

Run this on your machine, against your real vesta.duckdb, with the real
cafef_company_list.json path. Paste the printed output back -- that's the
real evidence F001b needs to move from `active` to `passing`, per this
project's "confirmed means pasted stdout" standard. Nothing this script
prints should be trusted until it's actually been run for real.

Usage:
    ./.venv/bin/python scratch/run_f001b_live_xref.py \
        --db db/vesta.duckdb \
        --cafef-json cafef_company_list.json \
        [--write]   # omit --write for a dry-run report only

Design notes:
- Read-only by default (--write is opt-in) so a first run is safe to do
  without deciding the target-table question yet.
- Fails loudly (raises, non-zero exit) on any DB/schema problem rather
  than printing a partial report and looking like success.
- Does NOT touch core.dim_symbol's existing rows or schema -- writes to a
  new, separate core.dim_symbol_cafef table (additive only, no PRIMARY KEY
  change to any existing table, so no migration is required per
  conventions.md's "Schema changes that touch a PRIMARY KEY" rule).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.cafef_symbol_directory import (
    find_new_non_otc_symbols,
    find_otc_only_symbols,
    parse_directory,
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS core.dim_symbol_cafef (
    symbol      VARCHAR NOT NULL,
    org_name    VARCHAR,
    exchange    VARCHAR NOT NULL,
    center_id   INTEGER NOT NULL,
    is_vn30     BOOLEAN,
    is_hnx30    BOOLEAN,
    slug_base   VARCHAR,
    source      VARCHAR NOT NULL,
    fetched_at  TIMESTAMP NOT NULL,
    raw_json    VARCHAR,
    PRIMARY KEY (symbol)
);
"""


def load_real_vnstock_symbols(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Reads the REAL, already-crawled core.dim_symbol table. Raises if the
    table doesn't exist or is empty -- an empty vnstock symbol set would
    silently make every cafef symbol look like a "new" one, which is wrong,
    not a legitimate zero-overlap finding.
    """
    try:
        rows = con.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
    except duckdb.CatalogException as exc:
        raise RuntimeError(
            "core.dim_symbol not found. This script must be run against the "
            "real vesta.duckdb where F001 has already been crawled -- not a "
            "fresh/empty database."
        ) from exc

    symbols = {r[0] for r in rows}
    if not symbols:
        raise RuntimeError(
            "core.dim_symbol exists but returned zero rows. Refusing to "
            "proceed -- an empty vnstock symbol set would make every cafef "
            "symbol look like a real gap, which is not a trustworthy result."
        )
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, help="Path to the real vesta.duckdb")
    parser.add_argument("--cafef-json", required=True, help="Path to cafef_company_list.json")
    parser.add_argument("--write", action="store_true", help="Actually write core.dim_symbol_cafef")
    args = parser.parse_args()

    con = duckdb.connect(args.db, read_only=not args.write)

    vnstock_symbols = load_real_vnstock_symbols(con)
    print(f"Real core.dim_symbol row count (distinct symbols): {len(vnstock_symbols)}")

    raw_entries = json.loads(Path(args.cafef_json).read_text(encoding="utf-8"))
    cafef_df = parse_directory(raw_entries)
    print(f"cafef directory entries parsed: {len(cafef_df)}")
    print("Exchange breakdown:", cafef_df["exchange"].value_counts().to_dict())

    otc_gap = find_otc_only_symbols(cafef_df, vnstock_symbols)
    print(f"\nREAL OTC-only gap (cafef OTC symbols absent from real dim_symbol): {len(otc_gap)}")

    non_otc_gap = find_new_non_otc_symbols(cafef_df, vnstock_symbols)
    if len(non_otc_gap) > 0:
        print(
            f"\nWARNING: {len(non_otc_gap)} non-OTC cafef symbols are "
            f"absent from vnstock's dim_symbol. This was expected to be ~0 "
            f"(HOSE/HNX/UPCOM should already be covered by F001). Sample:"
        )
        print(non_otc_gap[["symbol", "exchange", "org_name"]].head(10).to_string(index=False))
    else:
        print("\nNon-OTC symbols: 0 unexpected gaps (matches expectation).")

    if args.write:
        con.execute(CREATE_TABLE_SQL)
        write_df = pd.concat([otc_gap, non_otc_gap], ignore_index=True)
        con.execute("DELETE FROM core.dim_symbol_cafef WHERE source = 'cafef'")
        con.register("write_df", write_df)
        con.execute(
            "INSERT INTO core.dim_symbol_cafef "
            "SELECT symbol, org_name, exchange, center_id, is_vn30, is_hnx30, "
            "slug_base, source, fetched_at, raw_json FROM write_df"
        )
        n = con.execute("SELECT COUNT(*) FROM core.dim_symbol_cafef").fetchone()[0]
        print(f"\nWrote {n} rows to core.dim_symbol_cafef.")
    else:
        print("\n(dry run -- pass --write to persist to core.dim_symbol_cafef)")

    con.close()


if __name__ == "__main__":
    main()