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


# Confirmed 2026-08-31 by direct inspection: foreign-domiciled investment
# funds/vehicles, all CenterId=8 (OTC). NOT equities, but no reliable
# keyword or prefix rule catches them -- "Capital" alone is a false-positive
# trap (e.g. BCG "Bamboo Capital" and CRC "Create Capital Việt Nam" are
# real operating-company equities, not funds). An explicit, verified
# allowlist is used instead of a heuristic for this specific category.
FOREIGN_FUND_SYMBOLS = {
    "ASEANSF", "DCVEIL", "DCVGF", "DRAGON", "DWSVF", "FTSEETF",
    "GICSINGAPORE", "JFVOF", "LIONGVF", "MEKONGCAP", "PXPVEEF", "PYNMFE",
    "VCVNI", "VCVNL", "VCVOF", "VINACAP", "VNMETF", "WASATCH",
}


def _instrument_type(symbol: str, org_name: str) -> str:
    """cafef's directory mixes real equities with covered warrants, bonds,
    Vietnamese-domiciled funds/ETFs, and foreign-domiciled investment
    funds -- not just OTC/HOSE/HNX/UPCOM equities:
    - 142 covered warrants (confirmed 2026-08-31, org_name "Chứng quyền",
      all CenterId=1/HOSE).
    - 79 bonds (confirmed 2026-08-31, org_name "Trái phiếu"/"Trái Phiếu",
      CenterId 1 [HOSE, n=1] and 2 [HNX, n=78], never OTC/UPCOM).
    - 28 Vietnamese funds/ETFs (org_name starting "Quỹ" or "Chứng chỉ quỹ").
    - 18 foreign-domiciled investment funds/vehicles (confirmed 2026-08-31
      via FOREIGN_FUND_SYMBOLS, all CenterId=8/OTC) -- e.g. Dragon Capital,
      VinaCapital, JPMorgan Vietnam Opportunities Fund, GIC/Government of
      Singapore. These do not share a reliable name pattern with each
      other or with real equities (many real equities legitimately use
      "Capital" in their name, e.g. "Bamboo Capital", "Create Capital Việt
      Nam") -- a keyword heuristic here would misclassify real companies,
      so an explicit verified symbol list is used instead.

    IMPORTANT, confirmed by direct inspection: a naive substring check for
    "quỹ" anywhere in the name is WRONG -- 47 real equities (asset-
    management companies, e.g. "Công ty Cổ phần Quản lý quỹ AIC") legitimately
    mention "quỹ" in their name without being fund instruments themselves.
    Only a startswith("Quỹ") or startswith("Chứng chỉ quỹ") match is a real
    Vietnamese fund instrument; anything else containing "quỹ" is a real
    equity.

    None of covered_warrant/bond/fund would ever appear in vnstock's
    Reference.equity.list() -- treating any of them as a "missing equity"
    gap is a false positive. Flagged, not dropped, per the
    raw-payload-preserving convention.
    """
    name = org_name.strip()
    if symbol.strip().upper() in FOREIGN_FUND_SYMBOLS:
        return "fund"
    if name.startswith("Chứng quyền"):
        return "covered_warrant"
    if name.startswith(("Chứng chỉ quỹ", "Quỹ")):
        return "fund"
    if name.lower().startswith("trái phiếu"):
        return "bond"
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
                "instrument_type": _instrument_type(entry["Symbol"], entry["Title"]),
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
    """The actual gap this feature exists to close: cafef OTC-tier
    EQUITIES with zero vnstock coverage. Returns only rows where
    exchange == 'OTC' AND instrument_type == 'equity' AND the symbol is
    absent from vnstock's dim_symbol.

    FIXED 2026-08-31: this previously did not filter by instrument_type at
    all, so the OTC gap count silently included non-equity OTC entries
    (18 confirmed foreign investment funds, e.g. Dragon Capital,
    VinaCapital -- see FOREIGN_FUND_SYMBOLS). A raw "772 OTC symbols
    missing from dim_symbol" count would have overstated the real
    OTC-equity gap by including these.
    """
    otc = cafef_df[(cafef_df["exchange"] == "OTC") & (cafef_df["instrument_type"] == "equity")]
    return otc[~otc["symbol"].isin(vnstock_symbols)].copy()


def find_new_non_otc_symbols(cafef_df: pd.DataFrame, vnstock_symbols: set[str]) -> pd.DataFrame:
    """Non-OTC symbols cafef has that vnstock's dim_symbol doesn't -- this is
    a different, weaker claim than find_otc_only_symbols (OTC is a KNOWN
    vnstock gap; a missing HOSE/HNX/UPCOM symbol would be unexpected and
    worth a closer look, not an assumed-safe supplement).

    Excludes instrument_type in {'covered_warrant', 'bond', 'fund'} --
    none of these are ever returned by vnstock's equity endpoints, so all
    three would show up here as false-positive "gaps" otherwise (142
    warrants + 79 bonds + 28 funds/ETFs confirmed real, 2026-08-31).
    """
    non_otc = cafef_df[
        (cafef_df["exchange"] != "OTC") & (cafef_df["instrument_type"] == "equity")
    ]
    return non_otc[~non_otc["symbol"].isin(vnstock_symbols)].copy()