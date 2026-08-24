"""Pilot-universe export for staged crawling.

CONFIRMED live (2026-08-22): `Reference().equity.list_by_group(group=
'VN30', source='kbs')` is a real method (introspected signature; default
group is literally 'VN30'). Its return shape was reported (2026-08-23,
not yet independently re-confirmed by me against a live call) to be a
pd.Series, not a DataFrame -- fetch_group_symbols() below handles both
shapes rather than assuming one, and fails loudly with the real type/
columns printed if neither matches, rather than guessing wrong silently.

FALLBACK, if VN30 group lookup fails for any reason: accepts a manual
comma-separated symbol list via --symbols, so the pilot plan isn't
blocked on this one API call working perfectly on the first try.

API key resolution order: $VNSTOCK_API_KEY env var first, then
~/.vnstock/api_key.json (vnstock's own local key-cache file, used if you
previously ran a vnstock command that saved your key there) as a
fallback -- never hardcoded in this file.
"""
from __future__ import annotations

import json
import os
import sys
import pathlib

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"
VNSTOCK_KEY_CACHE_FILE = pathlib.Path.home() / ".vnstock" / "api_key.json"

# UNCONFIRMED which of these is real if the return value turns out to be
# a DataFrame -- see module docstring.
SYMBOL_COLUMN_ALIASES = ["symbol", "ticker", "stock_code"]


def _resolve_api_key() -> str:
    """$VNSTOCK_API_KEY first; falls back to vnstock's own local key-cache
    file if present. Never hardcode a key in this file -- see
    DECISIONS.md on the two keys already leaked into this repo's history.
    """
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if api_key:
        return api_key

    if VNSTOCK_KEY_CACHE_FILE.exists():
        try:
            cached = json.loads(VNSTOCK_KEY_CACHE_FILE.read_text(encoding="utf-8"))
            cached_key = cached.get("api_key")
            if cached_key:
                print(f"Using cached API key from {VNSTOCK_KEY_CACHE_FILE}")
                return str(cached_key)
        except (json.JSONDecodeError, OSError):
            pass

    raise RuntimeError(
        f"{REQUIRED_ENV_VAR} is not set and no cached key found at "
        f"{VNSTOCK_KEY_CACHE_FILE}. Export {REQUIRED_ENV_VAR} before running this script."
    )


def _authenticate() -> None:
    api_key = _resolve_api_key()
    import vnstock

    vnstock.change_api_key(api_key)


def fetch_group_symbols(group: str = "VN30") -> list[str]:
    """Live call. Returns the symbol list for a named index group (e.g.
    VN30). Handles both a pd.Series and a pd.DataFrame return shape;
    raises with the real type/columns if neither matches, rather than
    guessing.
    """
    _authenticate()
    import vnstock

    ref = vnstock.Reference()
    result = ref.equity.list_by_group(group=group)

    if isinstance(result, pd.Series):
        return sorted(result.astype(str).unique().tolist())

    if isinstance(result, pd.DataFrame):
        symbol_col = next((c for c in SYMBOL_COLUMN_ALIASES if c in result.columns), None)
        if symbol_col is None:
            raise ValueError(
                f"Could not find a symbol column in list_by_group(group={group!r}) "
                f"DataFrame output. Columns present: {list(result.columns)}. Update "
                f"SYMBOL_COLUMN_ALIASES with the real name rather than guessing, "
                f"or use --symbols to supply a manual list instead."
            )
        return sorted(result[symbol_col].astype(str).unique().tolist())

    raise TypeError(
        f"list_by_group(group={group!r}) returned an unexpected type: {type(result)}. "
        f"Expected pd.Series or pd.DataFrame. Inspect this live and update "
        f"fetch_group_symbols() rather than guessing, or use --symbols instead."
    )


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