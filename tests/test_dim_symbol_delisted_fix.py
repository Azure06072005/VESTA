from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawlers.dim_symbol import KNOWN_EXCHANGE_VALUES, build_dim_symbol


def _exchange_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _industry_df() -> pd.DataFrame:
    return pd.DataFrame([{"symbol": "BBC", "industry_code": "35", "industry_name": "Food"}])


def test_known_exchange_values_matches_confirmed_live_set() -> None:
    assert KNOWN_EXCHANGE_VALUES == {"HOSE", "HNX", "UPCOM", "DELISTED"}


def test_is_delisted_true_for_delisted_exchange() -> None:
    df = build_dim_symbol(
        _exchange_df([{"symbol": "BBC", "organ_name": "Bibica", "exchange": "DELISTED"}]),
        _industry_df(),
    )
    row = df.iloc[0]
    assert bool(row["is_delisted"]) is True
    assert pd.isna(row["delisted_date"])  # genuinely unknown -- never fabricated


def test_is_delisted_false_for_active_exchange() -> None:
    df = build_dim_symbol(
        _exchange_df([{"symbol": "VIC", "organ_name": "Vingroup", "exchange": "HOSE"}]),
        pd.DataFrame([{"symbol": "VIC"}]),
    )
    assert bool(df.iloc[0]["is_delisted"]) is False


def test_unrecognized_exchange_raises_loudly() -> None:
    with pytest.raises(ValueError, match="unrecognized exchange"):
        build_dim_symbol(
            _exchange_df([{"symbol": "MYSTERY1", "organ_name": "X", "exchange": "XHNF"}]),
            pd.DataFrame([{"symbol": "MYSTERY1"}]),
        )


def test_null_exchange_raises_loudly() -> None:
    with pytest.raises(ValueError, match="NULL exchange"):
        build_dim_symbol(
            _exchange_df([{"symbol": "MBB12106", "organ_name": "Bond", "exchange": None}]),
            pd.DataFrame([{"symbol": "MBB12106"}]),
        )


def test_all_four_known_exchanges_accepted_without_error() -> None:
    df = build_dim_symbol(
        _exchange_df(
            [
                {"symbol": "A", "organ_name": "A Co", "exchange": "HOSE"},
                {"symbol": "B", "organ_name": "B Co", "exchange": "HNX"},
                {"symbol": "C", "organ_name": "C Co", "exchange": "UPCOM"},
                {"symbol": "D", "organ_name": "D Co", "exchange": "DELISTED"},
            ]
        ),
        pd.DataFrame([{"symbol": s} for s in "ABCD"]),
    )
    assert len(df) == 4
    assert df.set_index("symbol")["is_delisted"].to_dict() == {
        "A": False,
        "B": False,
        "C": False,
        "D": True,
    }