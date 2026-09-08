"""Tests for F104: Machine Learning Feature Engineering and Dataset Preparation."""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from etl import db  # noqa: E402
from pipeline.ml_features import (  # noqa: E402
    build_feature_dataframe,
    calculate_forward_targets,
    extract_fundamental_features,
    extract_price_momentum_features,
    extract_text_features,
    split_temporal_dataset,
)


def test_extract_text_features():
    # Positive headline
    pos_res = extract_text_features("FPT loi nhuan tang truong ky luc nam 2024")
    assert pos_res["sentiment_score"] > 0
    assert pos_res["sentiment_class"] == "positive"
    assert pos_res["sentiment_pos_count"] >= 1
    assert pos_res["headline_word_count"] == 9

    # Negative headline
    neg_res = extract_text_features("Doanh nghiep thua lo nang nề bi phong toa tai khoan")
    assert neg_res["sentiment_score"] < 0
    assert neg_res["sentiment_class"] == "negative"
    assert neg_res["sentiment_neg_count"] >= 1

    # Empty headline
    empty_res = extract_text_features("")
    assert empty_res["sentiment_score"] == 0.0
    assert empty_res["sentiment_class"] == "neutral"
    assert empty_res["headline_char_len"] == 0


def test_extract_price_momentum_strictly_backward_looking(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_mom.duckdb")

    # Seed 25 historical bars for FPT
    base_date = dt.date(2024, 1, 30)
    for i in range(30):
        d = base_date - dt.timedelta(days=(30 - i))
        # Day 29 is 2024-01-29, day 30 is 2024-01-30. Add day 31 in future (2024-01-31)
        price = 100.0 + i  # Increasing price
        con.execute(
            "INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume, fetched_at) "
            "VALUES ('FPT', ?, ?, ?, ?, ?, 1000, '2024-02-01')",
            [d, price, price + 1, price - 1, price],
        )

    # Injected future price bar that should NEVER be visible
    future_date = base_date + dt.timedelta(days=1)
    con.execute(
        "INSERT INTO core.market_ohlcv_daily (symbol, date, open, high, low, close, volume, fetched_at) "
        "VALUES ('FPT', ?, 999.0, 999.0, 999.0, 999.0, 1000, '2024-02-01')",
        [future_date],
    )

    features = extract_price_momentum_features(con, "FPT", base_date)
    assert features["mom_1d"] is not None
    assert features["mom_5d"] is not None
    assert features["mom_20d"] is not None
    assert features["vol_20d"] is not None

    # Verify that future price 999.0 was NOT included in momentum
    assert features["mom_1d"] < 1.0  # If future 999.0 leaked in, mom would be huge (>8.0)


def test_extract_fundamental_features_parses_json_safely():
    # Valid fundamentals JSON with various key conventions
    valid_json = json.dumps({"PE": 15.5, "pb": 2.1, "rt_roe": 0.22})
    res = extract_fundamental_features(valid_json)
    assert res["pe_ratio"] == 15.5
    assert res["pb_ratio"] == 2.1
    assert res["roe"] == 0.22

    # Null / empty JSON
    assert extract_fundamental_features(None) == {"pe_ratio": None, "pb_ratio": None, "roe": None}
    assert extract_fundamental_features("invalid json string") == {"pe_ratio": None, "pb_ratio": None, "roe": None}


def test_calculate_forward_targets():
    # Up movement: p0=100, p5=105 (+5%)
    res = calculate_forward_targets(p0=100.0, p1=101.0, p5=105.0, p30=110.0)
    assert pytest.approx(res["target_ret_t1"]) == 0.01
    assert pytest.approx(res["target_ret_t5"]) == 0.05
    assert pytest.approx(res["target_ret_t30"]) == 0.10
    assert res["target_dir_t5"] == 1

    # Down movement: p0=100, p5=90 (-10%)
    res_down = calculate_forward_targets(p0=100.0, p1=99.0, p5=90.0, p30=85.0)
    assert pytest.approx(res_down["target_ret_t5"]) == -0.10
    assert res_down["target_dir_t5"] == -1

    # Flat movement: p0=100, p5=100.2 (+0.2%, within 0.5% threshold)
    res_flat = calculate_forward_targets(p0=100.0, p1=100.0, p5=100.2, p30=100.0)
    assert res_flat["target_dir_t5"] == 0

    # Missing future prices
    res_none = calculate_forward_targets(p0=100.0, p1=None, p5=None, p30=None)
    assert res_none["target_ret_t5"] is None
    assert res_none["target_dir_t5"] is None


def test_split_temporal_dataset_no_leakage():
    df = pd.DataFrame(
        {
            "symbol": ["FPT", "FPT", "FPT"],
            "effective_date": [dt.date(2023, 5, 1), dt.date(2024, 6, 1), dt.date(2025, 3, 1)],
            "feature": [1, 2, 3],
        }
    )
    train, val, test = split_temporal_dataset(
        df,
        train_end=dt.date(2023, 12, 31),
        val_end=dt.date(2024, 12, 31),
    )
    assert len(train) == 1
    assert len(val) == 1
    assert len(test) == 1

    assert train["effective_date"].max() <= dt.date(2023, 12, 31)
    assert val["effective_date"].min() > dt.date(2023, 12, 31)
    assert val["effective_date"].max() <= dt.date(2024, 12, 31)
    assert test["effective_date"].min() > dt.date(2024, 12, 31)


def test_build_feature_dataframe_end_to_end(tmp_path):
    con = db.bootstrap_schema(tmp_path / "test_pipe.duckdb")

    # Seed basic pit event
    con.execute("INSERT INTO core.dim_symbol (symbol, organ_name, fetched_at) VALUES ('FPT', 'FPT Corp', '2024-01-01')")
    con.execute(
        "INSERT INTO core.market_ohlcv_daily VALUES ('FPT', '2024-01-02', 100.0, 105.0, 99.0, 102.0, 500000, '2024-01-02 16:00:00')"
    )
    con.execute(
        "INSERT INTO core.pit_events VALUES ('FPT', 'https://example.com/fpt1', '2024-01-02 10:00:00', "
        "'FPT loi nhuan tang truong manh', NULL, 102.0, 103.0, 107.0, 115.0, '{\"PE\": 16.0}', '2023-12-31', '2024-01-02 12:00:00')"
    )

    feat_df = build_feature_dataframe(con, symbols=["FPT"])
    assert not feat_df.empty
    assert len(feat_df) == 1
    row = feat_df.iloc[0]

    assert row["symbol"] == "FPT"
    assert row["sentiment_score"] > 0
    assert row["pe_ratio"] == 16.0
    assert pytest.approx(row["target_ret_t5"]) == (107.0 - 102.0) / 102.0
    assert row["target_dir_t5"] == 1
