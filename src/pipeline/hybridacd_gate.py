"""src/pipeline/hybridacd_gate.py

Top-level alias for src/pipeline/f3xx_modeling/hybridacd_gate.py.
Provides HybridACDConsistencyGate and VietnameseFinancialFastAdversarialNegator.
"""
from pipeline.f3xx_modeling.hybridacd_gate import (
    VietnameseFinancialFastAdversarialNegator,
    HybridACDConsistencyGate,
    GateResult,
    FINANCIAL_ANTONYM_PAIRS,
    DENIAL_PREFIXES,
)

__all__ = [
    "VietnameseFinancialFastAdversarialNegator",
    "HybridACDConsistencyGate",
    "GateResult",
    "FINANCIAL_ANTONYM_PAIRS",
    "DENIAL_PREFIXES",
]
