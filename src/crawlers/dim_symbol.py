"""F001: dim_symbol reference crawler.

SCHEMA CORRECTED 2026-08-31 (supersedes the 2026-08-11 note below, which is
stale): a fresh live call to vnstock_data==3.2.2's
Reference().equity.list_by_exchange() returns columns
['symbol', 'exchange', 'organ_name', 'organ_short_name', 'icb_code_lv2']
-- there is NO 'type' column in the current API version. exchange takes
exactly 4 confirmed values today: HOSE, HNX, UPCOM, DELISTED -- confirmed
live 2026-08-31, 1,751 total (818 UPCOM + 405 HOSE + 299 HNX + 229 DELISTED).

DELISTED-STATUS FIX (2026-08-31): exchange=='DELISTED' is a REAL, live
signal vnstock_data exposes -- confirmed against BBC and BCG, both real
delisted HOSE equities, both returned with exchange='DELISTED'. The
2026-08-11 "vnstock does not expose delisted symbols" finding below was
tested only against free vnstock==4.0.5 and never re-tested against
vnstock_data, despite fetch_raw() already preferring vnstock_data when
installed. is_delisted is now derived from exchange=='DELISTED'.
delisted_date itself remains NULL -- vnstock_data's DELISTED bucket is a
status flag, not an actual date, and this crawler will not fabricate one.
This closes the boolean part of the original survivorship-bias gap
(filtering delisted from active symbols is now possible) even though the
exact delisted_date remains genuinely unavailable.

CONTAMINATION FOUND & EXPLAINED (2026-08-31): core.dim_symbol previously
held 3,418 rows (single fetched_at timestamp, confirmed via
scratch/diagnose_dim_symbol_contamination.py -- no rogue writer, one
write_dim_symbol() call), including 1,469 NULL-exchange rows (real bonds,
e.g. MBB12106) and 14 rows with an undocumented exchange='XHNF' value. A
fresh call today reproduces NEITHER -- a one-time artifact of whatever
vnstock_data version/behavior existed at that historical crawl (real
version drift; project notes elsewhere document 3.2.7, but 3.2.2 is what
was actually installed when this was investigated), not a bug in this
repo's own code. write_dim_symbol() now validates exchange against
KNOWN_EXCHANGE_VALUES and fails loudly on anything unrecognized, so a
future recurrence is caught immediately rather than sitting undetected.
See DECISIONS.md 2026-08-31 entries for the full investigation trail.

--- Original 2026-08-11 docstring (STALE, kept for history) ---
Schema confirmed live against vnstock==4.0.5 on 2026-08-11 (see
DECISIONS.md "Build order..." entry and discover_vnstock_schema.py output):

    Reference().equity.list_by_exchange() ->
        symbol, organ_name, en_organ_name, exchange, type, id
    Reference().industry.sectors() ->
        symbol, industry_code, industry_name

dim_symbol = left join of the two on `symbol`.

KNOWN GAP (as of 2026-08-11): vnstock's unified API does not expose
delisted symbols. Three attempted call shapes
(`list_by_group(group='DELISTED')`, `list(show_delisted=True)`,
`list(status='delisted')`) all failed against a live key. `delisted_date`
is therefore always NULL in this crawler's output -- this is a real,
logged gap (see DECISIONS.md), not a placeholder to quietly fill in later.
F001's survivorship-bias verification assertion cannot pass until an
alternative delisted-symbol source is chosen and logged as its own
DECISIONS.md entry.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import pathlib

import pandas as pd

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db

REQUIRED_ENV_VAR = "VNSTOCK_API_KEY"

DIM_SYMBOL_COLUMNS = [
    "symbol", 
    "organ_name", 
    "en_organ_name", 
    "exchange", 
    "industry_code", 
    "industry_name", 
    "delisted_date", 
    "is_delisted",
    "fetched_at",
]

# Confirmed live 2026-08-31. An unrecognized exchange value must fail
# loudly rather than being silently written -- this is exactly the
# validation gap that let 1,469 bond rows and 14 'XHNF' rows sit
# undetected in core.dim_symbol for an unknown period of time.
KNOWN_EXCHANGE_VALUES = {"HOSE", "HNX", "UPCOM", "DELISTED"}

def _authenticate() -> None:
    """Read the vnstock API key from the environment. Never hardcode it,
    never accept it as a function argument from a caller that might log it.
    """
    db.load_env()
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{REQUIRED_ENV_VAR} is not set. Export it before running this "
            f"crawler -- credentials never go in code or configs/."
        )
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    if hasattr(vs, "change_api_key"):
        vs.change_api_key(api_key)

def fetch_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Returns (exchange_df, industry_df) exactly as vnstock returns them,
    with no transformation -- transformation is build_dim_symbol()'s job
    so that logic stays testable without network access.
    """
    _authenticate()
    try:
        import vnstock_data as vs
    except ImportError:
        import vnstock as vs  # type: ignore[no-redef]

    ref = vs.Reference()
    exchange_df = ref.equity.list_by_exchange()
    industry_df = ref.industry.sectors()
    return exchange_df, industry_df

def build_dim_symbol(exchange_df: pd.DataFrame, industry_df: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: left-join exchange listing with industry sectors on
    `symbol`, append delisted_date (always NULL -- see module docstring)
    and fetched_at. No network access -- fully unit-testable with
    synthetic DataFrames.
    """
    for required_col, df, name in [
        ("symbol", exchange_df, "exchange_df"),
        ("symbol", industry_df, "industry_df"),
    ]:
        if required_col not in df.columns:
            raise ValueError(f"{name} missing required columns '{required_col}'")

    ind = industry_df.copy()
    if "icb_code" in ind.columns and "industry_code" not in ind.columns:
        ind = ind.rename(columns={"icb_code": "industry_code", "icb_name": "industry_name"})
    if "industry_code" not in ind.columns:
        ind["industry_code"] = None
    if "industry_name" not in ind.columns:
        ind["industry_name"] = None

    # Deduplicate industry_df on symbol (e.g. vnstock_data exposes multi-level ICB)
    ind_dedup = ind.drop_duplicates(subset=["symbol"])[["symbol", "industry_code", "industry_name"]]

    ex = exchange_df.copy()
    if "en_organ_name" not in ex.columns:
        ex["en_organ_name"] = ex.get("organ_short_name", ex.get("organ_name", ex["symbol"]))

    merged = ex.merge(ind_dedup, on="symbol", how="left")
    merged["organ_name"] = merged["organ_name"].fillna(merged["en_organ_name"]).fillna(merged["symbol"])
    merged["delisted_date"] = pd.NaT  # genuinely unknown -- see module docstring, not fabricated
    merged["is_delisted"] = merged["exchange"] == "DELISTED"
    merged["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    bad_exchanges = set(merged["exchange"].dropna().unique()) - KNOWN_EXCHANGE_VALUES
    if bad_exchanges:
        raise ValueError(
            f"build_dim_symbol encountered unrecognized exchange value(s) "
            f"{bad_exchanges}, not in KNOWN_EXCHANGE_VALUES={KNOWN_EXCHANGE_VALUES}. "
            f"This is exactly the pattern that let 1,469 bond rows and 14 "
            f"'XHNF' rows into core.dim_symbol undetected (2026-08-31) -- "
            f"failing loudly rather than silently writing an unrecognized "
            f"instrument type into the equity reference table. Confirm the "
            f"new value is a real exchange before extending "
            f"KNOWN_EXCHANGE_VALUES, per this crawler's evidence discipline."
        )
    null_exchange_count = merged["exchange"].isna().sum()
    if null_exchange_count:
        raise ValueError(
            f"build_dim_symbol found {null_exchange_count} row(s) with a "
            f"NULL exchange value -- the 2026-08-31 contamination incident "
            f"was exactly this pattern (1,469 NULL-exchange bond rows). "
            f"Refusing to write until this is understood, not silently "
            f"dropping or keeping them."
        )

    out = merged[DIM_SYMBOL_COLUMNS].copy()

    dupes = out["symbol"].duplicated().sum()
    if dupes:
        raise ValueError(
            f"build_dim_symbol produced {dupes} duplicate symbol(s) -- "
            f"dim_symbol must be on row per symbol."
        )

    return out

def write_dim_symbol(df: pd.DataFrame, con: "duckdb.DuckDBPyConnection | None" = None) -> int:
    """Validate + write to core.dim_symbol. Fails loudly on schema
    mismatch per conventions.md error-handling pattern -- never silently
    substitutes or drops rows.
    """
    missing = set(DIM_SYMBOL_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"dim_symbol DataFrame missing columns: {missing}")

    con = con or db.bootstrap_schema()
    con.execute("DELETE FROM core.dim_symbol")
    con.register("dim_symbol_df", df[DIM_SYMBOL_COLUMNS])
    cols = ", ".join(DIM_SYMBOL_COLUMNS)
    con.execute(f"INSERT INTO core.dim_symbol ({cols}) SELECT {cols} FROM dim_symbol_df")
    con.unregister("dim_symbol_df")
    return len(df)

def run() -> int:
    """Entry point: fetch live, transform, write. Returns row count written."""
    exchange_df, industry_df = fetch_raw()
    dim_symbol = build_dim_symbol(exchange_df, industry_df)
    return write_dim_symbol(dim_symbol)


if __name__ == "__main__":
    n = run()
    print(f"F001 dim_symbol: wrote {n} rows to core.dim_symbol")