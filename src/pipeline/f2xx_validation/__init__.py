"""F2xx Tier: Statistical Edge Validation, Robustness & Regime Auditing.

Modules:
- backtest_meanreversion (F201): Sentiment mean-reversion hypothesis backtest.
- sentiment_lexicon (F201 support): Starter dictionary scoring and headline classification.
- f201_robustness_check (F202): Statistical robustness, multi-way cluster bootstrap, sign-flip check.
- f202b_dsr_pbo (F202b): Formal Deflated Sharpe Ratio & CSCV Probability of Backtest Overfitting.
- f203_regime_audit (F203): Regime-conditional validity audit across 16 historical cycles.
"""
from __future__ import annotations

from . import backtest_meanreversion, f201_robustness_check, f202b_dsr_pbo, sentiment_lexicon

__all__ = [
    "backtest_meanreversion",
    "f201_robustness_check",
    "f202b_dsr_pbo",
    "sentiment_lexicon",
]
