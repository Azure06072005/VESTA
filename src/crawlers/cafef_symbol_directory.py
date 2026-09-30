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
import logging
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import duckdb
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers.db_writer import DEFAULT_TARGET_DB, ResilientDuckDBWriter

logger = logging.getLogger("cafef_symbol_directory")

CAFEF_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS core.dim_symbol_cafef (
    symbol         VARCHAR NOT NULL PRIMARY KEY,
    org_name       VARCHAR NOT NULL,
    exchange       VARCHAR NOT NULL,
    center_id      INTEGER NOT NULL,
    is_vn30        BOOLEAN NOT NULL,
    is_hnx30       BOOLEAN NOT NULL,
    slug_base      VARCHAR NOT NULL,
    source         VARCHAR NOT NULL DEFAULT 'cafef',
    fetched_at     TIMESTAMP NOT NULL,
    raw_json       VARCHAR NOT NULL,
    tradeable_flag BOOLEAN NOT NULL DEFAULT FALSE,
    subuniverse    VARCHAR NOT NULL DEFAULT 'OTC'
);

ALTER TABLE core.dim_symbol_cafef ADD COLUMN IF NOT EXISTS tradeable_flag BOOLEAN DEFAULT FALSE;
ALTER TABLE core.dim_symbol_cafef ADD COLUMN IF NOT EXISTS subuniverse VARCHAR DEFAULT 'OTC';

CREATE OR REPLACE VIEW core.v_symbol_universe AS
SELECT 
    symbol, 
    organ_name as org_name, 
    exchange, 
    is_delisted,
    TRUE as tradeable_flag, 
    'LISTED' as subuniverse,
    'vnstock' as source,
    fetched_at
FROM core.dim_symbol
UNION ALL
SELECT 
    symbol, 
    org_name, 
    exchange, 
    TRUE as is_delisted,
    tradeable_flag, 
    subuniverse,
    source,
    fetched_at
FROM core.dim_symbol_cafef;
"""

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

# Confirmed 2026-09-02: exactly 9 real market-index "symbols" (VNINDEX,
# VN30INDEX, etc.) exist in the directory, verifiable by a distinctive
# RedirectUrl pattern unique to index history pages -- not equities.
INDEX_URL_MARKER = "lich-su-giao-dich-symbol-"

# Confirmed 2026-09-02: covered warrants normally have a "Chứng quyền..."
# title, but 2 real entries (CMSN2101, CVPB2314) have a blank or
# self-referential title instead, missing that marker. Their symbol shape
# (C + 2-4 letters + 4 digits) matches 131 OTHER already-confirmed
# "Chứng quyền"-titled warrants out of 133 total matches -- a reliable
# secondary signal for exactly this fallback case, not a broad heuristic
# (it is only applied when the title itself gives no other signal).
WARRANT_CODE_PATTERN = re.compile(r"^C[A-Z]{2,4}\d{4}$")


def _is_blank_title(name: str) -> bool:
    """Confirmed 2026-09-02: 5 directory entries have a title that is
    literally the two-character string "''" (a placeholder artifact in
    cafef's own data), not a truly empty string -- a plain `not name`
    check misses these. Checked explicitly rather than assumed.
    """
    return name == "" or name in ("''", '""')


def _instrument_type(symbol: str, org_name: str, redirect_url: str) -> str:
    """cafef's directory mixes real equities with covered warrants, bonds,
    Vietnamese-domiciled funds/ETFs, foreign-domiciled investment funds,
    market indices, and a small number of blank/uninformative-title
    entries -- not just OTC/HOSE/HNX/UPCOM equities:
    - 142 covered warrants (org_name "Chứng quyền", all CenterId=1/HOSE)
      PLUS 2 more caught by WARRANT_CODE_PATTERN with a blank/
      self-referential title instead of the normal prefix (CMSN2101,
      CVPB2314) -- confirmed 2026-09-02.
    - 79 bonds (org_name "Trái phiếu"/"Trái Phiếu").
    - 46 funds/ETFs (28 Vietnamese-prefixed + 18 confirmed foreign via
      FOREIGN_FUND_SYMBOLS).
    - 9 market indices (confirmed 2026-09-02 via INDEX_URL_MARKER, a
      RedirectUrl pattern unique to index history pages -- NOT
      self-referential title alone, since JACCAR is a REAL OTC equity
      [Jaccar Holdings] whose real company name happens to equal its
      ticker; title==symbol alone is not a reliable non-equity signal).
    - A handful of entries (confirmed 2026-09-02: CDICThanhBinh, DATC,
      HIEU, HUD3) have a blank/placeholder title and match none of the
      above rules -- classified 'unknown' rather than guessed as equity,
      per the "encode gaps honestly" convention. Do NOT assume these are
      safe equities; a human should look them up individually if they
      matter for a specific downstream use.

    None of covered_warrant/bond/fund/index would ever appear in
    vnstock's Reference.equity.list() -- treating any of them as a
    "missing equity" gap is a false positive. Flagged, not dropped, per
    the raw-payload-preserving convention.
    """
    name = org_name.strip()
    sym = symbol.strip().upper()

    if INDEX_URL_MARKER in redirect_url:
        return "index"
    if sym in FOREIGN_FUND_SYMBOLS:
        return "fund"
    if name.startswith("Chứng quyền"):
        return "covered_warrant"
    if name.startswith(("Chứng chỉ quỹ", "Quỹ")):
        return "fund"
    if name.lower().startswith("trái phiếu"):
        return "bond"
    if WARRANT_CODE_PATTERN.match(sym) and (_is_blank_title(name) or name.upper() == sym):
        # Only reached when the title gave no positive signal at all --
        # a blank/placeholder or self-referential title on a
        # warrant-shaped symbol.
        return "covered_warrant"
    if _is_blank_title(name):
        return "unknown"
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

        exchange_str = CENTER_ID_TO_EXCHANGE[center_id]
        inst_type = _instrument_type(entry["Symbol"], entry["Title"], entry["RedirectUrl"])
        is_otc = (exchange_str == "OTC")

        rows.append(
            {
                "symbol": entry["Symbol"].strip().upper(),
                "org_name": entry["Title"].strip(),
                "exchange": exchange_str,
                "center_id": center_id,
                "instrument_type": inst_type,
                "is_vn30": bool(entry["IsVn30"]),
                "is_hnx30": bool(entry["IsHnx30"]),
                "slug_base": _slug_base(entry["RedirectUrl"]),
                "source": "cafef",
                "fetched_at": fetched_at,
                "raw_json": json.dumps(entry, ensure_ascii=False),
                "tradeable_flag": False,
                "subuniverse": "OTC" if is_otc else ("UNLISTED" if inst_type == "equity" else "NON_EQUITY"),
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


def build_dim_symbol_cafef(
    cafef_df: pd.DataFrame | list[dict],
    vnstock_symbols: Optional[set[str]] = None,
) -> pd.DataFrame:
    """Xây dựng DataFrame bảng bổ sung core.dim_symbol_cafef (F001b).
    
    Phân tách rõ ràng:
    - 750 mã OTC: subuniverse = 'OTC', tradeable_flag = False
      (Cách ly khỏi các mô hình backtest thanh khoản để chống nhiễu thực thi).
    - 234 mã non-OTC ngoài vnstock: subuniverse = 'UNLISTED', tradeable_flag = False.
    """
    if isinstance(cafef_df, list):
        cafef_df = parse_directory(cafef_df)

    if vnstock_symbols is None:
        # Tự động lấy danh sách mã niêm yết từ core.dim_symbol nếu có CSDL
        for cand in [
            DEFAULT_TARGET_DB,
            str(PROJECT_ROOT / "db" / "vesta_backup.duckdb"),
            str(PROJECT_ROOT / "db" / "vesta.duckdb"),
        ]:
            if os.path.exists(cand):
                try:
                    c = duckdb.connect(cand, read_only=True)
                    rows = c.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
                    c.close()
                    vnstock_symbols = {r[0].upper() for r in rows}
                    break
                except Exception:
                    pass
        if vnstock_symbols is None:
            # Fallback lấy các mã niêm yết HOSE/HNX/UPCOM có trong cafef_df
            vnstock_symbols = set(
                cafef_df[cafef_df["exchange"].isin(["HOSE", "HNX", "UPCOM"])]["symbol"]
            )

    otc_gap = find_otc_only_symbols(cafef_df, vnstock_symbols)
    otc_gap = otc_gap.copy()
    otc_gap["tradeable_flag"] = False
    otc_gap["subuniverse"] = "OTC"

    non_otc_gap = find_new_non_otc_symbols(cafef_df, vnstock_symbols)
    non_otc_gap = non_otc_gap.copy()
    non_otc_gap["tradeable_flag"] = False
    non_otc_gap["subuniverse"] = "UNLISTED"

    df_out = pd.concat([otc_gap, non_otc_gap], ignore_index=True)
    return df_out


build_dim_symbol_cafef_df = build_dim_symbol_cafef


def write_dim_symbol_cafef(
    df: Optional[pd.DataFrame] = None,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    writer: Optional[ResilientDuckDBWriter | duckdb.DuckDBPyConnection] = None,
) -> int:
    """Ghi bảng bổ sung core.dim_symbol_cafef và tạo/làm mới VIEW core.v_symbol_universe."""
    if con is None and isinstance(writer, duckdb.DuckDBPyConnection):
        con = writer
        writer = None

    if df is None:
        file_path = PROJECT_ROOT / "cafef_company_list.json"
        with open(file_path, "r", encoding="utf-8") as f:
            raw_entries = json.load(f)
        cafef_df = parse_directory(raw_entries)
        vnstock_symbols = set()
        if con is not None:
            try:
                rows = con.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
                vnstock_symbols = {r[0].upper() for r in rows}
            except Exception:
                pass
        df = build_dim_symbol_cafef(cafef_df, vnstock_symbols)

    required_cols = {"symbol", "org_name", "exchange", "center_id", "source"}
    if not required_cols.issubset(set(df.columns)):
        raise ValueError(f"DataFrame thiếu các cột bắt buộc: {required_cols - set(df.columns)}")

    write_df = df.copy()
    if "tradeable_flag" not in write_df.columns:
        write_df["tradeable_flag"] = write_df["exchange"] != "OTC"
    if "subuniverse" not in write_df.columns:
        write_df["subuniverse"] = write_df["exchange"].apply(lambda x: "OTC" if x == "OTC" else "UNLISTED")

    cols_to_write = [
        "symbol", "org_name", "exchange", "center_id", "is_vn30", "is_hnx30",
        "slug_base", "source", "fetched_at", "raw_json", "tradeable_flag", "subuniverse"
    ]

    if con is not None:
        con.execute(CAFEF_SCHEMA_DDL)
        con.execute("DELETE FROM core.dim_symbol_cafef WHERE source = 'cafef'")
        con.register("df_cafef_view", write_df[cols_to_write])
        con.execute("""
            INSERT INTO core.dim_symbol_cafef
            SELECT * FROM df_cafef_view
        """)
        con.unregister("df_cafef_view")
        cnt = con.execute("SELECT count(*) FROM core.dim_symbol_cafef").fetchone()[0]
        return cnt

    writer = writer or ResilientDuckDBWriter()

    def _action(c: duckdb.DuckDBPyConnection):
        c.execute(CAFEF_SCHEMA_DDL)
        c.execute("DELETE FROM core.dim_symbol_cafef WHERE source = 'cafef'")
        c.register("df_cafef_view", write_df[cols_to_write])
        c.execute("""
            INSERT INTO core.dim_symbol_cafef
            SELECT * FROM df_cafef_view
        """)
        c.unregister("df_cafef_view")
        return len(write_df)

    cnt = writer.execute_with_retry(_action)
    try:
        writer.atomic_ingest_buffer()
    except Exception as e:
        logger.debug("Atomic ingest skipped/deferred: %s", e)
    return cnt


def run(
    target_db: Optional[str] = None,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    json_path: Optional[str] = None,
) -> int:
    """Hàm chạy chính của crawler F001b cafef_symbol_directory."""
    logger.info(">>> [F001b] Bắt đầu đồng bộ danh bạ CafeF & phân tách OTC-Subuniverse...")
    file_path = pathlib.Path(json_path) if json_path else (PROJECT_ROOT / "cafef_company_list.json")
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file danh bạ: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw_entries = json.load(f)

    cafef_df = parse_directory(raw_entries)

    vnstock_symbols: set[str] = set()
    con_to_use = con
    close_con = False
    if con_to_use is None:
        db_cand = target_db or DEFAULT_TARGET_DB
        for cand in [db_cand, str(PROJECT_ROOT / "db" / "vesta_backup.duckdb")]:
            if os.path.exists(cand):
                try:
                    con_to_use = duckdb.connect(cand, read_only=True)
                    close_con = True
                    break
                except Exception:
                    continue

    if con_to_use is not None:
        try:
            rows = con_to_use.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
            vnstock_symbols = {r[0].upper() for r in rows}
        finally:
            if close_con:
                con_to_use.close()

    df_supplement = build_dim_symbol_cafef(cafef_df, vnstock_symbols)
    otc_cnt = int((df_supplement["subuniverse"] == "OTC").sum())
    unlisted_cnt = int((df_supplement["subuniverse"] == "UNLISTED").sum())
    logger.info(
        "Đã phân tách: %d mã OTC-Subuniverse (tradeable_flag=False), %d mã Unlisted.",
        otc_cnt,
        unlisted_cnt,
    )

    if con is not None:
        cnt = write_dim_symbol_cafef(df_supplement, con=con)
    else:
        writer = ResilientDuckDBWriter(target_db=target_db or DEFAULT_TARGET_DB)
        cnt = write_dim_symbol_cafef(df_supplement, writer=writer)

    logger.info(">>> [F001b] Hoàn tất nạp core.dim_symbol_cafef: %d bản ghi.", cnt)
    return cnt


def get_tradeable_symbols(
    con: Optional[duckdb.DuckDBPyConnection] = None,
    target_db: str = DEFAULT_TARGET_DB,
) -> set[str]:
    """Tra cứu tập hợp toàn bộ các mã cổ phiếu ĐƯỢC PHÉP GIAO DỊCH (tradeable_flag=True).
    
    Tự động loại bỏ 100% 750 mã OTC để bảo vệ mô hình backtest khỏi nhiễu thực thi.
    """
    close_con = False
    con_to_use = con
    if con_to_use is None:
        for cand in [target_db, str(PROJECT_ROOT / "db" / "vesta_backup.duckdb"), str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb")]:
            if os.path.exists(cand):
                try:
                    con_to_use = duckdb.connect(cand, read_only=True)
                    close_con = True
                    break
                except Exception:
                    continue

    if con_to_use is None:
        return set()

    try:
        try:
            rows = con_to_use.execute("SELECT symbol FROM core.v_symbol_universe WHERE tradeable_flag = TRUE").fetchall()
            return {r[0].upper() for r in rows}
        except Exception:
            rows = con_to_use.execute("SELECT symbol FROM core.dim_symbol WHERE exchange != 'OTC'").fetchall()
            return {r[0].upper() for r in rows}
    finally:
        if close_con and con_to_use:
            con_to_use.close()


def get_otc_symbols(
    con: Optional[duckdb.DuckDBPyConnection] = None,
    target_db: str = DEFAULT_TARGET_DB,
) -> set[str]:
    """Tra cứu tập hợp 750 mã thuộc OTC-Subuniverse (tradeable_flag=False)."""
    close_con = False
    con_to_use = con
    if con_to_use is None:
        for cand in [target_db, str(PROJECT_ROOT / "db" / "vesta_backup.duckdb"), str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb")]:
            if os.path.exists(cand):
                try:
                    con_to_use = duckdb.connect(cand, read_only=True)
                    close_con = True
                    break
                except Exception:
                    continue

    if con_to_use is None:
        return set()

    try:
        rows = con_to_use.execute("SELECT symbol FROM core.dim_symbol_cafef WHERE exchange = 'OTC'").fetchall()
        return {r[0].upper() for r in rows}
    finally:
        if close_con and con_to_use:
            con_to_use.close()