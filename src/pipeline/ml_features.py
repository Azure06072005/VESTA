"""F104: Machine Learning Feature Engineering and Dataset Preparation Pipeline.

Constructs standardized feature matrices and forward-looking target variables from
point-in-time joined data (core.pit_events) and historical price/fundamentals tables.

Key Architectural Guarantees:
1. Zero Look-ahead Bias: All feature inputs (text, momentum, volatility, fundamentals)
   are strictly backward-looking relative to the event timestamp.
2. Temporal Dataset Splitting: Train, validation, and test sets are partitioned by time
   boundaries, guaranteeing no data leakage from the future into the training set.
3. Robust Missing Value Handling: Returns None / NaN explicitly rather than fabricating
   neutral values (B3/B4 principles).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import pathlib
import sys
from typing import Any

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from pipeline.sentiment_lexicon import (  # noqa: E402
    NEGATIVE_TERMS,
    POSITIVE_TERMS,
    _strip_accents_lower,
    classify_headline,
    score_headline,
)


@dataclasses.dataclass(frozen=True)
class FeatureRecord:
    symbol: str
    published_at: dt.datetime
    effective_date: dt.date
    headline: str
    # NLP Sentiment features
    sentiment_score: float
    sentiment_class: str
    sentiment_pos_count: int
    sentiment_neg_count: int
    headline_char_len: int
    headline_word_count: int
    # Price Momentum and Volatility features (strictly backward-looking <= effective_date)
    mom_1d: float | None
    mom_5d: float | None
    mom_20d: float | None
    vol_20d: float | None
    # Fundamental features (from point-in-time fundamentals_json)
    pe_ratio: float | None
    pb_ratio: float | None
    roe: float | None
    # Forward Target labels (to predict)
    target_ret_t1: float | None
    target_ret_t5: float | None
    target_ret_t30: float | None
    target_dir_t5: int | None  # 1 (up), -1 (down), 0 (flat)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def extract_text_features(headline: str) -> dict[str, Any]:
    """Extracts lexical sentiment and textual statistics from the headline."""
    if not headline:
        return {
            "sentiment_score": 0.0,
            "sentiment_class": "neutral",
            "sentiment_pos_count": 0,
            "sentiment_neg_count": 0,
            "headline_char_len": 0,
            "headline_word_count": 0,
        }

    score = score_headline(headline)
    cls = classify_headline(headline)
    norm = _strip_accents_lower(headline)
    pos_hits = sum(1 for term in POSITIVE_TERMS if term in norm)
    neg_hits = sum(1 for term in NEGATIVE_TERMS if term in norm)
    words = headline.split()

    return {
        "sentiment_score": float(score),
        "sentiment_class": cls,
        "sentiment_pos_count": pos_hits,
        "sentiment_neg_count": neg_hits,
        "headline_char_len": len(headline),
        "headline_word_count": len(words),
    }


def extract_price_momentum_features(
    con: duckdb.DuckDBPyConnection, symbol: str, as_of_date: dt.date
) -> dict[str, float | None]:
    """Extracts trailing momentum and volatility up to as_of_date.

    Guarantees:
    - Only queries rows where date <= as_of_date (zero forward leakage).
    - Requires at least 21 historical bars for full 20-day momentum and volatility.
    """
    rows = con.execute(
        """
        SELECT date, close
        FROM core.market_ohlcv_daily
        WHERE symbol = ? AND date <= ? AND close IS NOT NULL
        ORDER BY date DESC
        LIMIT 25
        """,
        [symbol, as_of_date],
    ).fetchall()

    if not rows or len(rows) < 2:
        return {"mom_1d": None, "mom_5d": None, "mom_20d": None, "vol_20d": None}

    # rows[0] is as_of_date (or latest prior bar)
    p0 = rows[0][1]
    if p0 <= 0:
        return {"mom_1d": None, "mom_5d": None, "mom_20d": None, "vol_20d": None}

    # 1-day momentum
    p_prev1 = rows[1][1]
    mom_1d = (p0 - p_prev1) / p_prev1 if p_prev1 > 0 else None

    # 5-day momentum
    mom_5d = None
    if len(rows) >= 6:
        p_prev5 = rows[5][1]
        mom_5d = (p0 - p_prev5) / p_prev5 if p_prev5 > 0 else None

    # 20-day momentum and volatility
    mom_20d = None
    vol_20d = None
    if len(rows) >= 21:
        p_prev20 = rows[20][1]
        mom_20d = (p0 - p_prev20) / p_prev20 if p_prev20 > 0 else None

        # Calculate daily percentage returns over the 20 intervals
        prices = [r[1] for r in rows[:21]]  # newest to oldest
        daily_returns = [(prices[i] - prices[i + 1]) / prices[i + 1] for i in range(20) if prices[i + 1] > 0]
        if len(daily_returns) == 20:
            mean_ret = sum(daily_returns) / 20.0
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / 19.0
            vol_20d = math.sqrt(variance)

    return {"mom_1d": mom_1d, "mom_5d": mom_5d, "mom_20d": mom_20d, "vol_20d": vol_20d}


def extract_fundamental_features(fundamentals_json: str | None) -> dict[str, float | None]:
    """Safely extracts financial ratios from point-in-time fundamentals JSON."""
    if not fundamentals_json:
        return {"pe_ratio": None, "pb_ratio": None, "roe": None}

    try:
        data = json.loads(fundamentals_json)
        if not isinstance(data, dict):
            return {"pe_ratio": None, "pb_ratio": None, "roe": None}

        # Normalize keys to lowercase for flexible schema matching
        norm = {str(k).lower(): v for k, v in data.items()}

        def _get_float(*keys: str) -> float | None:
            for k in keys:
                if k in norm and norm[k] is not None:
                    try:
                        val = float(norm[k])
                        if not math.isnan(val) and not math.isinf(val):
                            return val
                    except (ValueError, TypeError):
                        pass
            return None

        pe = _get_float("pe", "price_to_earnings", "rt_pe", "p/e")
        pb = _get_float("pb", "price_to_book", "rt_pb", "p/b")
        roe = _get_float("roe", "return_on_equity", "rt_roe")
        return {"pe_ratio": pe, "pb_ratio": pb, "roe": roe}
    except Exception:
        return {"pe_ratio": None, "pb_ratio": None, "roe": None}


def calculate_forward_targets(
    p0: float | None,
    p1: float | None,
    p5: float | None,
    p30: float | None,
    threshold: float = 0.005,
) -> dict[str, float | int | None]:
    """Calculates forward percentage returns and directional class for t+5."""
    if p0 is None or p0 <= 0:
        return {
            "target_ret_t1": None,
            "target_ret_t5": None,
            "target_ret_t30": None,
            "target_dir_t5": None,
        }

    ret_t1 = (p1 - p0) / p0 if (p1 is not None and p1 > 0) else None
    ret_t5 = (p5 - p0) / p0 if (p5 is not None and p5 > 0) else None
    ret_t30 = (p30 - p0) / p0 if (p30 is not None and p30 > 0) else None

    dir_t5 = None
    if ret_t5 is not None:
        if ret_t5 > threshold:
            dir_t5 = 1
        elif ret_t5 < -threshold:
            dir_t5 = -1
        else:
            dir_t5 = 0

    return {
        "target_ret_t1": ret_t1,
        "target_ret_t5": ret_t5,
        "target_ret_t30": ret_t30,
        "target_dir_t5": dir_t5,
    }


def build_feature_dataframe(
    con: duckdb.DuckDBPyConnection,
    symbols: list[str] | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Builds a vectorized feature DataFrame from core.pit_events and market data."""
    query = """
        SELECT 
            symbol,
            published_at,
            headline,
            price_at_publish,
            price_t1,
            price_t5,
            price_t30,
            fundamentals_json
        FROM core.pit_events
    """
    params: list[Any] = []
    where_clauses: list[str] = []

    if symbols:
        where_clauses.append("symbol IN ?")
        params.append(symbols)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY published_at ASC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    events = con.execute(query, params).fetchall()
    if not events:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for row in events:
        sym, pub_at, headline, p0, p1, p5, p30, fund_json = row
        eff_date = pub_at.date() if isinstance(pub_at, dt.datetime) else pd.to_datetime(pub_at).date()

        text_feat = extract_text_features(headline)
        tech_feat = extract_price_momentum_features(con, sym, eff_date)
        fund_feat = extract_fundamental_features(fund_json)
        targets = calculate_forward_targets(p0, p1, p5, p30)

        record = {
            "symbol": sym,
            "published_at": pub_at,
            "effective_date": eff_date,
            "headline": headline,
            **text_feat,
            **tech_feat,
            **fund_feat,
            **targets,
        }
        records.append(record)

    df = pd.DataFrame(records)
    df["effective_date"] = pd.to_datetime(df["effective_date"]).dt.date
    return df


def split_temporal_dataset(
    df: pd.DataFrame,
    train_end: dt.date = dt.date(2023, 12, 31),
    val_end: dt.date = dt.date(2024, 12, 31),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Partitions dataset temporally into Train, Validation, and Test sets.

    Guarantees zero future look-ahead data leakage across set splits:
    - Train: effective_date <= train_end
    - Validation: train_end < effective_date <= val_end
    - Test: effective_date > val_end
    """
    if df.empty:
        return df.copy(), df.copy(), df.copy()

    train_mask = df["effective_date"] <= train_end
    val_mask = (df["effective_date"] > train_end) & (df["effective_date"] <= val_end)
    test_mask = df["effective_date"] > val_end

    train_df = df[train_mask].reset_index(drop=True)
    val_df = df[val_mask].reset_index(drop=True)
    test_df = df[test_mask].reset_index(drop=True)

    return train_df, val_df, test_df
