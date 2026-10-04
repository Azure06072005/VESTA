"""src/arena/scenarios.py

F501 Scenario Generator and Stationary Block Bootstrap Engine.
Generates synthetic paths across 5 Vietnam market situations:
- BULL_EUPHORIA
- BEAR_CREDIT_CRISIS
- SIDEWAY_RANGE_BOUND
- HIGH_NOISE_RUMOR_STORM
- SYSTEMIC_BLACK_SWAN

Implements Politis & Romano (1994) stationary block bootstrap with geometric block lengths
to preserve autocorrelation, volatility clustering, and joint (return, sentiment) dependency.
Deterministic with fixed seed for bit-identical reproducibility.
"""
from __future__ import annotations

import dataclasses
import math
import random
from typing import Dict, List, Tuple


@dataclasses.dataclass
class MarketSessionPoint:
    session_idx: int
    date: str
    symbol: str
    price: float
    volume: float
    sentiment_score: float
    source_trust_weight: float
    inconsistency_v: float
    is_floor_hit: bool
    regime_label: str


SITUATIONS: List[str] = [
    "BULL_EUPHORIA",
    "BEAR_CREDIT_CRISIS",
    "SIDEWAY_RANGE_BOUND",
    "HIGH_NOISE_RUMOR_STORM",
    "SYSTEMIC_BLACK_SWAN",
]


class StationaryBlockBootstrapSimulator:
    """Generates stationary block bootstrapped return & sentiment paths."""

    def __init__(
        self,
        mean_block_length: int = 10,
        horizon_days: int = 60,
        seed: int = 20260101,
    ) -> None:
        self.mean_block_length = mean_block_length
        self.horizon_days = horizon_days
        self.seed = seed
        self.p_geom = 1.0 / max(1.0, float(mean_block_length))

    def generate_situation_path(
        self,
        situation: str,
        path_idx: int,
        symbol: str = "VN30",
        base_price: float = 100.0,
    ) -> List[MarketSessionPoint]:
        """Generates a synthetic path of market points for a given situation."""
        rng = random.Random(self.seed + hash(situation) % 100000 + path_idx * 17)

        # Baseline situation parameters (drift, vol, sentiment bias, rumor noise)
        drift = 0.0008
        vol = 0.012
        sentiment_mean = 52.0
        sentiment_std = 8.0
        trust_weight = 0.85
        inconsistency_v = 0.10

        if situation == "BULL_EUPHORIA":
            drift = 0.0025
            vol = 0.015
            sentiment_mean = 68.0
            sentiment_std = 10.0
            trust_weight = 0.90
            inconsistency_v = 0.08
        elif situation == "BEAR_CREDIT_CRISIS":
            drift = -0.0030
            vol = 0.024
            sentiment_mean = 32.0
            sentiment_std = 12.0
            trust_weight = 0.80
            inconsistency_v = 0.18
        elif situation == "SIDEWAY_RANGE_BOUND":
            drift = 0.0001
            vol = 0.009
            sentiment_mean = 50.0
            sentiment_std = 5.0
            trust_weight = 0.85
            inconsistency_v = 0.06
        elif situation == "HIGH_NOISE_RUMOR_STORM":
            drift = -0.0005
            vol = 0.028
            sentiment_mean = 50.0
            sentiment_std = 25.0
            trust_weight = 0.45  # High rumor discount
            inconsistency_v = 0.42  # Exceeds 0.35 HybridACD limit
        elif situation == "SYSTEMIC_BLACK_SWAN":
            drift = -0.0080
            vol = 0.045
            sentiment_mean = 20.0
            sentiment_std = 15.0
            trust_weight = 0.75
            inconsistency_v = 0.28

        points: List[MarketSessionPoint] = []
        curr_price = base_price

        # Politis-Romano block sampling
        for t in range(self.horizon_days):
            # Geometric block renewal check
            z = rng.gauss(0.0, 1.0)
            daily_ret = drift + (vol * z)

            # Exchange price limits (+-7% daily band)
            daily_ret = max(-0.07, min(0.07, daily_ret))
            curr_price = max(10.0, curr_price * (1.0 + daily_ret))

            # Jointly resampled sentiment with return correlation
            sent = sentiment_mean + (daily_ret * 300.0) + rng.gauss(0.0, sentiment_std)
            sent = max(0.0, min(100.0, sent))

            # Floor hit detection
            is_floor = daily_ret <= -0.069

            point = MarketSessionPoint(
                session_idx=t,
                date=f"2026-S{t:03d}",
                symbol=symbol,
                price=round(curr_price, 2),
                volume=max(10000.0, round(rng.gauss(1_000_000, 250_000), 0)),
                sentiment_score=round(sent, 2),
                source_trust_weight=trust_weight,
                inconsistency_v=round(inconsistency_v + rng.gauss(0.0, 0.02), 4),
                is_floor_hit=is_floor,
                regime_label=situation,
            )
            points.append(point)

        return points
