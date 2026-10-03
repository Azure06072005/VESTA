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
from pipeline.f3xx_modeling.hybridacd_multi_checkers import (
    FullKolmogorovFinancialEngine,
    MultiCheckerReport,
    FinancialMultiTupleGenerator,
    FINANCIAL_SYNONYM_PAIRS,
    FINANCIAL_CONSEQUENCE_MAP,
)
from pipeline.f3xx_modeling.self_supervised_adversarial import (
    SelfSupervisedKolmogorovLoss,
    AdversarialPerturbationEngine,
    SelfSupervisedAdversarialTrainer,
    AdversarialBatch,
    SelfSupervisedTelemetry,
)

__all__ = [
    "VietnameseFinancialFastAdversarialNegator",
    "HybridACDConsistencyGate",
    "GateResult",
    "FINANCIAL_ANTONYM_PAIRS",
    "DENIAL_PREFIXES",
    "FullKolmogorovFinancialEngine",
    "MultiCheckerReport",
    "FinancialMultiTupleGenerator",
    "FINANCIAL_SYNONYM_PAIRS",
    "FINANCIAL_CONSEQUENCE_MAP",
    "SelfSupervisedKolmogorovLoss",
    "AdversarialPerturbationEngine",
    "SelfSupervisedAdversarialTrainer",
    "AdversarialBatch",
    "SelfSupervisedTelemetry",
]

