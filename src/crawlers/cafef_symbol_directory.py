"""F001b: cafef.vn company directory -- cross-reference source for dim_symbol.

Confirmed live 2026-08-31 against a real cafef.vn directory export
(cafef_company_list.json, 3,016 entries, user-provided):

- CENTER_ID_TO_EXCHANGE mapping was NOT guessed -- derived by cross-checking
  each entry's RedirectUrl folder against its CenterId. CenterId=2 maps to
  folder "hastc" (HNX's legacy internal name), NOT "hnx" -- this would have
  been silently wrong if assumed from the modern exchange name alone.
- RedirectUrl slug format confirmed byte-identical to a live HAR capture for
  VIC: "/du-lieu/hose/vic-tap-doan-vingroup-cong-ty-co-phan.chn".
- IsVn30 flag confirmed correct against the real 30 VN30 constituents.
- This directory includes exchange=OTC (CenterId=8, 777 entries) which
  vnstock's Reference.equity.list() does not cover at all -- this is the
  real gap F001b exists to close, not new coverage for its own sake.

Raw-payload-preserving convention applies (conventions.md "Data engineering
patterns"): this source's schema is directory-shaped and cafef-controlled,
not confirmed stable long-term, so the full raw record is kept as JSON
alongside typed columns.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pandas as pd

# Confirmed 2026-08-31 by direct cross-check against real RedirectUrl
# folders -- do not extend this mapping without the same kind of check.
# An unrecognized CenterId must fail loudly (see parse_directory), never
# silently default to an exchange guess.
CENTER_ID_TO_EXCHANGE = {
    1: "HOSE",
    2: "HNX",  # cafef folder name is "hastc" (legacy), exchange itself is HNX
    8: "OTC",
    9: "UPCOM",
}

REQUIRED_FIELDS = ["Symbol", "Title", "RedirectUrl", "CenterId", "IsVn30", "IsHnx30"]


class UnknownCenterIdError(ValueError):
    """Raised when a directory entry has a CenterId outside the confirmed
    mapping. Per conventions.md error-handling pattern: fail loudly rather
    than silently guessing an exchange for an unrecognized code.
    """


def _slug_base(redirect_url: str) -> str:
    """Strip the trailing '.chn' to get the reusable base slug other
    per-symbol tabs (news/financials/leadership) attach a suffix to.
    """
    if not redirect_url.endswith(".chn"):
        raise ValueError(f"Unexpected RedirectUrl shape (no .chn suffix): {redirect_url!r}")
    return redirect_url[: -len(".chn")]


def _instrument_type(org_name: str) -> str:
    """cafef's directory mixes real equities with covered warrants (142
    confirmed entries, all CenterId=1/HOSE, org_name starting with "Chứng
    quyền" -- confirmed live 2026-08-31 against the real 3,016-entry file).
    Warrants are NOT equities and would never appear in vnstock's
    Reference.equity.list() -- treating them as a "missing equity symbol"
    gap would be a false positive. Flagged, not dropped, per the
    raw-payload-preserving convention -- downstream consumers decide
    whether to filter them out.
    """
    if org_name.strip().startswith("Chứng quyền"):
        return "covered_warrant"
    return "equity"


def parse_directory(raw_entries: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize the raw cafef directory JSON into a typed DataFrame.

    Raises UnknownCenterIdError loudly on any CenterId not in
    CENTER_ID_TO_EXCHANGE -- never silently drops or mis-maps a row.
    """
    rows = []
    fetched_at = dt.datetime.now(dt.timezone.utc)

    for entry in raw_entries:
        missing = [f for f in REQUIRED_FIELDS if f not in entry]
        if missing:
            raise ValueError(f"Directory entry missing required fields {missing}: {entry!r}")

        center_id = entry["CenterId"]
        if center_id not in CENTER_ID_TO_EXCHANGE:
            raise UnknownCenterIdError(
                f"CenterId={center_id!r} is not in the confirmed mapping "
                f"{CENTER_ID_TO_EXCHANGE}. Do not guess an exchange for this "
                f"row -- confirm the real folder via RedirectUrl first, per "
                f"the 2026-08-31 evidence discipline for this crawler."
            )

        rows.append(
            {
                "symbol": entry["Symbol"].strip().upper(),
                "org_name": entry["Title"].strip(),
                "exchange": CENTER_ID_TO_EXCHANGE[center_id],
                "center_id": center_id,
                "instrument_type": _instrument_type(entry["Title"]),
                "is_vn30": bool(entry["IsVn30"]),
                "is_hnx30": bool(entry["IsHnx30"]),
                "slug_base": _slug_base(entry["RedirectUrl"]),
                "source": "cafef",
                "fetched_at": fetched_at,
                "raw_json": json.dumps(entry, ensure_ascii=False),
            }
        )

    df = pd.DataFrame(rows)
    dup_symbols = df["symbol"][df["symbol"].duplicated()].unique().tolist()
    if dup_symbols:
        raise ValueError(
            f"Duplicate symbols within a single cafef directory fetch: {dup_symbols}. "
            f"This would indicate a real data problem, not a code bug -- surfacing "
            f"loudly rather than silently deduping."
        )
    return df


def find_otc_only_symbols(cafef_df: pd.DataFrame, vnstock_symbols: set[str]) -> pd.DataFrame:
    """The actual gap this feature exists to close: cafef OTC-tier companies
    with zero vnstock coverage. Returns only rows where exchange == 'OTC'
    AND the symbol is absent from vnstock's dim_symbol.
    """
    otc = cafef_df[cafef_df["exchange"] == "OTC"]
    return otc[~otc["symbol"].isin(vnstock_symbols)].copy()


def find_new_non_otc_symbols(cafef_df: pd.DataFrame, vnstock_symbols: set[str]) -> pd.DataFrame:
    """Non-OTC symbols cafef has that vnstock's dim_symbol doesn't -- this is
    a different, weaker claim than find_otc_only_symbols (OTC is a KNOWN
    vnstock gap; a missing HOSE/HNX/UPCOM symbol would be unexpected and
    worth a closer look, not an assumed-safe supplement).

    Excludes instrument_type == 'covered_warrant' -- warrants are never
    returned by vnstock's equity endpoints, so they would always show up
    here as a false-positive "gap" otherwise (142 confirmed real cases,
    2026-08-31).
    """
    non_otc = cafef_df[
        (cafef_df["exchange"] != "OTC") & (cafef_df["instrument_type"] == "equity")
    ]
    return non_otc[~non_otc["symbol"].isin(vnstock_symbols)].copy()