"""Pilot-universe export for staged crawling.

CONFIRMED live (2026-08-22): `Reference().equity.list_by_group(group=
'VN30', source='kbs')` is a real method (introspected signature; default
group is literally 'VN30'). UNCONFIRMED: its actual return shape --
decorator-wrapped, so column names are unknown until a live call is made.
This script is defensive about that: it tries a handful of plausible
symbol-column names and fails loudly with the real columns printed if
none match, rather than guessing wrong silently.

FALLBACK, if VN30 group lookup fails for any reason: accepts a manual
comma-separated symbol list via --symbols, so the pilot plan isn't
blocked on this one API call working perfectly on the first try.
"""
from __future__ import annotations

import json
import os
import sys
import pathlib
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"

# UNCONFIRMED which of these is real -- see module docstring.
SYMBOL_COLUMN_ALIASES = ["symbol", "ticker", "stock_code"]


def _authenticate() -> None:
    if not os.environ.get(REQUIRED_ENV_VAR):
        key_path = pathlib.Path.home() / ".vnstock" / "api_key.json"
        if key_path.exists():
            with open(key_path, "r", encoding="utf-8") as f:
                os.environ[REQUIRED_ENV_VAR] = json.load(f).get("api_key", "")

    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if not api_key:
        raise RuntimeError(f"{REQUIRED_ENV_VAR} is not set. Export it before running this script.")
    import vnstock

    vnstock.change_api_key(api_key)


def fetch_group_symbols(group: str = "VN30") -> list[str]:
    """Live call. Returns the symbol list for a named index group (e.g.
    VN30). Handles pd.Series, pd.DataFrame, or list returns from vnstock.
    """
    _authenticate()
    import vnstock

    ref = vnstock.Reference()
    res = ref.equity.list_by_group(group=group)

    if isinstance(res, pd.Series):
        return sorted(res.dropna().astype(str).unique().tolist())
    elif isinstance(res, pd.DataFrame):
        symbol_col = next((c for c in SYMBOL_COLUMN_ALIASES if c in res.columns), None)
        if symbol_col is None:
            raise ValueError(
                f"Could not find a symbol column in list_by_group(group={group!r}) "
                f"output. Columns present: {list(res.columns)}. Update "
                f"SYMBOL_COLUMN_ALIASES with the real name rather than guessing, "
                f"or use --symbols to supply a manual list instead."
            )
        return sorted(res[symbol_col].dropna().astype(str).unique().tolist())
    elif isinstance(res, (list, tuple, set)):
        return sorted({str(s).strip() for s in res if str(s).strip()})
    else:
        raise TypeError(f"Unexpected return type from list_by_group: {type(res)}")


def export_symbols(symbols: list[str], output_path: str) -> int:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols) + "\n")
    return len(symbols)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Export a pilot symbol universe (VN30 by default) for staged crawling"
    )
    parser.add_argument("--group", default="VN30", help="index group to pull (default: VN30)")
    parser.add_argument(
        "--symbols",
        default=None,
        help="comma-separated manual symbol list -- bypasses the live group lookup entirely if the API call fails",
    )
    parser.add_argument("--out", default="scratch/pilot_symbols.txt")
    args = parser.parse_args()

    if args.symbols:
        symbol_list = sorted({s.strip().upper() for s in args.symbols.split(",") if s.strip()})
        print(f"Using manual symbol list ({len(symbol_list)} symbols), skipping live lookup.")
    else:
        symbol_list = fetch_group_symbols(args.group)

    n = export_symbols(symbol_list, args.out)
    print(f"Wrote {n} symbols to {args.out}")