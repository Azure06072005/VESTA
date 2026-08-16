"""F001: dim_symbol reference crawler.

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
    "fetched_at",
]

def _authenticate() -> None:
    """Read the vnstock API key from the environment. Never hardcode it,
    never accept it as a function argument from a caller that might log it.
    """
    api_key = os.environ.get(REQUIRED_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{REQUIRED_ENV_VAR} is not set. Export it before running this "
            f"crawler -- credentials never go in code or configs/."
        )
    import vnstock  # local import: keep vnstock optional for pure unit tests

    vnstock.change_api_key(api_key)

def fetch_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Live network call. Requires VNSTOCK_API_KEY to be set.

    Returns (exchange_df, industry_df) exactly as vnstock returns them,
    with no transformation -- transformation is build_dim_symbol()'s job
    so that logic stays testable without network access.
    """
    _authenticate()
    import vnstock

    ref = vnstock.Reference()
    exchange_df = ref.equity.list_by_exchange()
    industry_df = ref.industry.sectors()
    return exchange_df, industry_df

def build_dim_symbol(exchange_df: pd.DataFrame, industry_df:pd.DataFrame) -> pd.DataFrame:
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

    merged = exchange_df.merge(
        industry_df[["symbol", "industry_code", "industry_name"]],
        on="symbol", 
        how="left",
    )
    merged["delisted_date"] = pd.NaT
    merged["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

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
    con.execute("INSERT INTO core.dim_symbol SELECT * FROM dim_symbol_df")
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