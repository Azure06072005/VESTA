"""Before extending dim_symbol_cafef to cover the 150 orphan 'delisted
equity' tickers found in core.market_ohlcv_daily (F101 validation
failure, 2026-09-06), check whether they actually exist ANYWHERE in
cafef's current company directory at all -- regardless of instrument_type.

Two genuinely different situations require different fixes:
  (a) The ticker exists in cafef_company_list.json but was filtered out
      of dim_symbol_cafef because find_otc_only_symbols()/
      find_new_non_otc_symbols() only write instrument_type=='equity'
      rows for the OTC-gap use case -- this is a real, closeable gap by
      extending what gets WRITTEN, not a data-availability problem.
  (b) The ticker is genuinely absent from cafef's current directory
      entirely -- cafef's own directory reflects currently-relevant
      companies, and a long-delisted/dissolved entity may have simply
      dropped out of it. This is a real, sourced, permanent-until-a-
      better-source gap (same category as F001's original 2026-08-11
      delisted-date decision), NOT something "adding to dim_symbol_cafef"
      can fix -- there is nothing live to add.

Usage:
    ./.venv/bin/python scratch/diagnose_orphan_equity_source_availability.py --db db/vesta.duckdb --cafef-json cafef_company_list.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from crawlers.cafef_symbol_directory import parse_directory  # noqa: E402

# Confirmed patterns from this session's own evidence -- covered warrants,
# bonds, funds/indices all have recognizable shapes. A ticker NOT matching
# any of these and NOT already in dim_symbol is presumed to be a real
# equity candidate for this specific check.
WARRANT_LIKE = re.compile(r"^C[A-Z0-9]{6,9}$")
BOND_LIKE = re.compile(r"^[A-Z0-9]{3}[0-9]{5,6}$")
FUND_LIKE = re.compile(r"^(FU|E1)[A-Z0-9]+$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--cafef-json", required=True)
    args = parser.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    dim_symbols = set(con.execute("SELECT symbol FROM core.dim_symbol").fetchall())
    dim_symbols = {r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol").fetchall()}

    ohlcv_symbols = {
        r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.market_ohlcv_daily").fetchall()
    }
    orphans = ohlcv_symbols - dim_symbols

    # Isolate the "real equity, not a known derivative shape" subset --
    # this is what the report called the ~150 delisted-equity orphans.
    equity_shaped_orphans = {
        s for s in orphans
        if not WARRANT_LIKE.match(s) and not BOND_LIKE.match(s) and not FUND_LIKE.match(s)
    }
    print(f"Total orphans in market_ohlcv_daily: {len(orphans)}")
    print(f"Equity-shaped orphans (not warrant/bond/fund pattern): {len(equity_shaped_orphans)}")

    raw_entries = json.loads(pathlib.Path(args.cafef_json).read_text(encoding="utf-8"))
    cafef_symbols_any_type = {e["Symbol"].strip().upper() for e in raw_entries}

    present_in_cafef = equity_shaped_orphans & cafef_symbols_any_type
    absent_from_cafef = equity_shaped_orphans - cafef_symbols_any_type

    print(f"\n(a) Present in cafef_company_list.json (any instrument_type) "
          f"but filtered out of dim_symbol_cafef: {len(present_in_cafef)}")
    if present_in_cafef:
        cafef_df = parse_directory(raw_entries)
        present_rows = cafef_df[cafef_df["symbol"].isin(present_in_cafef)]
        print("  instrument_type breakdown for these:")
        print("  " + present_rows["instrument_type"].value_counts().to_string().replace("\n", "\n  "))
        print("  Sample:")
        print(present_rows[["symbol", "instrument_type", "exchange"]].head(10).to_string(index=False))

    print(f"\n(b) Genuinely ABSENT from cafef's current directory entirely: {len(absent_from_cafef)}")
    if absent_from_cafef:
        print("  These cannot be 'added to dim_symbol_cafef' -- there is no live source row")
        print("  to add. This is a real, sourced gap, same category as F001's original")
        print("  2026-08-11 delisted-date decision. Sample:")
        print(" ", sorted(absent_from_cafef)[:20])

    con.close()


if __name__ == "__main__":
    main()