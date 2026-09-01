from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.cafef_symbol_directory import (
    CENTER_ID_TO_EXCHANGE,
    UnknownCenterIdError,
    find_new_non_otc_symbols,
    find_otc_only_symbols,
    parse_directory,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "cafef_company_list.json"


@pytest.fixture(scope="module")
def real_directory() -> list[dict]:
    """Loads the real, user-provided 3,016-entry cafef directory export --
    not a synthetic fixture. Schema assertions below run against real data.
    """
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


SAMPLE_VIC_ENTRY = {
    "Symbol": "VIC",
    "Title": "Tập đoàn Vingroup - Công ty Cổ phần",
    "Description": "Tập đoàn Vingroup - Công ty Cổ phần",
    "AvatarUrl": "vic.jpg",
    "RedirectUrl": "/du-lieu/hose/vic-tap-doan-vingroup-cong-ty-co-phan.chn",
    "CenterId": 1,
    "Orderby": 1,
    "IsVn30": True,
    "IsHnx30": False,
}


def test_center_id_mapping_confirmed_values():
    assert CENTER_ID_TO_EXCHANGE == {1: "HOSE", 2: "HNX", 8: "OTC", 9: "UPCOM"}


def test_parse_directory_known_entry_shape():
    df = parse_directory([SAMPLE_VIC_ENTRY])
    row = df.iloc[0]
    assert row["symbol"] == "VIC"
    assert row["exchange"] == "HOSE"
    assert bool(row["is_vn30"]) is True
    assert bool(row["is_hnx30"]) is False
    assert row["slug_base"] == "/du-lieu/hose/vic-tap-doan-vingroup-cong-ty-co-phan"
    assert row["source"] == "cafef"
    assert json.loads(row["raw_json"])["Symbol"] == "VIC"


def test_unknown_center_id_raises_loudly():
    bad_entry = dict(SAMPLE_VIC_ENTRY, CenterId=99)
    with pytest.raises(UnknownCenterIdError):
        parse_directory([bad_entry])


def test_missing_required_field_raises():
    bad_entry = dict(SAMPLE_VIC_ENTRY)
    del bad_entry["RedirectUrl"]
    with pytest.raises(ValueError, match="missing required fields"):
        parse_directory([bad_entry])


def test_malformed_redirect_url_raises():
    bad_entry = dict(SAMPLE_VIC_ENTRY, RedirectUrl="/du-lieu/hose/vic-no-suffix")
    with pytest.raises(ValueError, match="Unexpected RedirectUrl shape"):
        parse_directory([bad_entry])


def test_duplicate_symbol_within_fetch_raises():
    with pytest.raises(ValueError, match="Duplicate symbols"):
        parse_directory([SAMPLE_VIC_ENTRY, SAMPLE_VIC_ENTRY])


def test_idempotent_parse_same_input_same_output_modulo_fetched_at():
    df1 = parse_directory([SAMPLE_VIC_ENTRY])
    df2 = parse_directory([SAMPLE_VIC_ENTRY])
    cols = [c for c in df1.columns if c != "fetched_at"]
    pd.testing.assert_frame_equal(df1[cols], df2[cols])


def test_find_otc_only_symbols_excludes_vnstock_covered():
    df = pd.DataFrame(
        [
            {"symbol": "AAOTC", "exchange": "OTC"},
            {"symbol": "VIC", "exchange": "HOSE"},
            {"symbol": "BBOTC", "exchange": "OTC"},
        ]
    )
    vnstock_symbols = {"VIC", "BBOTC"}  # BBOTC pretends to already be covered
    result = find_otc_only_symbols(df, vnstock_symbols)
    assert result["symbol"].tolist() == ["AAOTC"]


def test_find_new_non_otc_symbols_flags_unexpected_gap():
    df = pd.DataFrame(
        [
            {"symbol": "VIC", "exchange": "HOSE", "instrument_type": "equity"},
            {"symbol": "NEWCO", "exchange": "UPCOM", "instrument_type": "equity"},
        ]
    )
    vnstock_symbols = {"VIC"}
    result = find_new_non_otc_symbols(df, vnstock_symbols)
    assert result["symbol"].tolist() == ["NEWCO"]


# ---- Tests against the REAL uploaded directory (3,016 entries) ----


def test_real_directory_parses_without_error(real_directory):
    df = parse_directory(real_directory)
    assert len(df) == 3016


def test_real_directory_exchange_counts_match_confirmed_evidence(real_directory):
    df = parse_directory(real_directory)
    counts = df["exchange"].value_counts().to_dict()
    # Confirmed 2026-08-31 via direct inspection: CenterId Counter({9: 1150, 8: 777, 1: 645, 2: 444})
    assert counts == {"UPCOM": 1150, "OTC": 777, "HOSE": 645, "HNX": 444}


def test_real_directory_vn30_matches_known_constituents(real_directory):
    df = parse_directory(real_directory)
    vn30 = set(df[df["is_vn30"]]["symbol"])
    assert len(vn30) == 30
    # Spot-check a few real, well-known VN30 members rather than the full list,
    # to avoid this test silently going stale if VN30 membership changes.
    assert {"VIC", "VNM", "FPT", "VCB", "HPG"}.issubset(vn30)


def test_real_directory_no_unknown_center_ids(real_directory):
    # This test existing at all is the point: if cafef ever adds a 5th
    # CenterId, parse_directory must fail loudly, not silently mis-map it.
    df = parse_directory(real_directory)
    assert set(df["center_id"].unique()) == {1, 2, 8, 9}


def test_real_directory_otc_gap_is_the_documented_777(real_directory):
    df = parse_directory(real_directory)
    otc_symbols = set(df[df["exchange"] == "OTC"]["symbol"])
    assert len(otc_symbols) == 777
    # Simulate vnstock coverage containing zero of these OTC symbols,
    # matching the documented real gap (vnstock Reference.equity.list()
    # does not return OTC-tier symbols at all).
    fake_vnstock_symbols = set(df[df["exchange"] != "OTC"]["symbol"])
    gap = find_otc_only_symbols(df, fake_vnstock_symbols)
    assert len(gap) == 777


def test_covered_warrants_flagged_not_equity():
    warrant_entry = dict(
        SAMPLE_VIC_ENTRY,
        Symbol="MBB5MSSICEUCASH11",
        Title="Chứng quyền MBB/5M/SSI/C/EU/Cash-11",
    )
    df = parse_directory([warrant_entry])
    assert df.iloc[0]["instrument_type"] == "covered_warrant"


def test_real_directory_warrant_count_confirmed(real_directory):
    df = parse_directory(real_directory)
    warrants = df[df["instrument_type"] == "covered_warrant"]
    assert len(warrants) == 142
    assert set(warrants["exchange"].unique()) == {"HOSE"}


def test_find_new_non_otc_symbols_excludes_covered_warrants(real_directory):
    df = parse_directory(real_directory)
    # vnstock covers everything real (no gaps) -- only warrants should
    # remain unmatched if the exclusion works, and they must NOT appear.
    equity_non_otc_symbols = set(
        df[(df["exchange"] != "OTC") & (df["instrument_type"] == "equity")]["symbol"]
    )
    gap = find_new_non_otc_symbols(df, equity_non_otc_symbols)
    assert len(gap) == 0