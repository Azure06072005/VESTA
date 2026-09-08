"""Root-cause check for the ~456 apparent equity gap found by F001b's
cross-reference (2026-08-31).

CORRECTED 2026-08-31: the first version of this script guessed a vnstock
call shape (Vnstock().stock().listing.symbols_by_exchange(), forcing the
free `vnstock` package) instead of using the repo's real fetch_raw(). That
guess returned 1,751 -- suspiciously identical to F001's original 2026-08-11
evidence -- while core.dim_symbol holds 3,418 and full_universe_run.py's own
docstring expects "~3,446 active symbols". dim_symbol.py's real fetch_raw()
tries `vnstock_data` (paid) BEFORE falling back to free `vnstock` -- these
are plausibly two different data surfaces with different symbol counts.
The first run's "BBC/BCG dropped by F001" conclusion is UNRELIABLE because
it likely compared against the wrong (free-tier) surface, not the one that
actually populated core.dim_symbol. This version imports fetch_raw() from
the real module directly -- no reimplementation, no guessed call shape.

Usage:
    ./.venv/bin/python scratch/diagnose_f001_gap.py --db db/vesta.duckdb
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from crawlers import dim_symbol  # noqa: E402  -- the REAL module, real fetch_raw()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument(
        "--check-symbols",
        nargs="*",
        default=["BBC", "BCG", "BAOMINH", "TIENTHINH", "TOBUONG", "VIETTIEP"],
        help="Specific symbols to trace individually through both sides.",
    )
    args = parser.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    stored = {
        r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
    }
    print(f"core.dim_symbol stored row count: {len(stored)}")

    # Uses the REAL fetch_raw() -- whatever package (vnstock_data or vnstock)
    # it actually resolves to at runtime, exactly as F001 does in production.
    exchange_df, _industry_df = dim_symbol.fetch_raw()
    print(f"fetch_raw() resolved via: {dim_symbol.fetch_raw.__module__}")
    try:
        import vnstock_data
        print(f"Package loaded: vnstock_data ({getattr(vnstock_data, '__version__', 'unknown')})")
    except ImportError:
        try:
            import vnstock
            print(f"Package loaded: vnstock ({getattr(vnstock, '__version__', 'unknown')})")
        except ImportError:
            print("Package loaded: unknown")

    fresh_symbols = set(exchange_df["symbol"].astype(str).str.upper())
    print(f"Fresh live fetch_raw() symbol count (this run, right now): {len(fresh_symbols)}")

    only_in_fresh_not_stored = fresh_symbols - stored
    only_in_stored_not_fresh = stored - fresh_symbols

    print(f"\nIn fresh fetch_raw() but NOT in stored core.dim_symbol: {len(only_in_fresh_not_stored)}")
    print(f"In stored core.dim_symbol but NOT in fresh fetch_raw(): {len(only_in_stored_not_fresh)}")

    print("\n--- Per-symbol trace (the specific missing equities found earlier) ---")
    for sym in args.check_symbols:
        in_stored = sym in stored
        in_fresh = sym in fresh_symbols
        print(f"{sym:12s}  stored={in_stored!s:5s}  fresh_fetch_raw={in_fresh!s:5s}")

    print(
        "\nInterpretation:\n"
        "  - If a missing symbol shows fresh_fetch_raw=True: the SAME call "
        "F001 uses in production returns it today -- either the original "
        "crawl was run against a stale/smaller universe, or write_dim_symbol() "
        "has a real bug. Worth a second fresh dim_symbol.run() to see if the "
        "stored count changes.\n"
        "  - If a missing symbol shows fresh_fetch_raw=False: not returned by "
        "the real production call either -- a genuine, current upstream gap, "
        "same category as the OTC/delisted gaps, document it the same way."
    )

    con.close()


if __name__ == "__main__":
    main()
