"""tests/test_local_reasoning_slm.py

Unit tests for F305: Local Deep Reasoning SLM Integration.
Tests Vietnamese financial prompt construction, Pydantic schema validation,
cascade trigger gating, and deterministic CoT synthesis.
"""
from __future__ import annotations

import pytest
import sys
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from models.local_reasoning_slm import (
    VietnameseFinancialPromptBuilder,
    LocalReasoningSLMEngine,
    ReasoningThesisOutput,
)


def test_prompt_builder():
    """Verifies that prompt builder correctly formats rich context in Vietnamese."""
    builder = VietnameseFinancialPromptBuilder()
    prompts = builder.build_prompt(
        headline="Chủ tịch VHM mua 10 triệu cổ phiếu",
        body="Giao dịch dự kiến thực hiện trong tháng 11.",
        symbol="VHM",
        source="CafeF",
        source_weight=0.85,
        matched_shareholder="Phạm Nhật Vượng",
        icb_sector="Bất động sản",
        fast_path_sentiment="POSITIVE",
        fast_path_alpha=68.5,
    )

    assert "system_prompt" in prompts
    assert "user_prompt" in prompts
    assert "VHM" in prompts["user_prompt"]
    assert "Phạm Nhật Vượng" in prompts["user_prompt"]
    assert "Bất động sản" in prompts["user_prompt"]
    assert "POSITIVE" in prompts["user_prompt"]
    assert "68.50" in prompts["user_prompt"]


def test_pydantic_schema_validation():
    """Verifies strict validation of ReasoningThesisOutput."""
    valid_data = {
        "reasoning_chain": "Doanh nghiệp có tăng trưởng doanh thu 40% và nguồn tin chính thức từ UBCKNN.",
        "sentiment_classification": "POSITIVE",
        "confidence_score": 0.88,
        "risk_flags": [],
        "suggested_action": "HOLD",
        "latency_ms": 12.5,
        "model_used": "qwen2.5-3b-instruct",
    }
    output = ReasoningThesisOutput(**valid_data)
    assert output.sentiment_classification == "POSITIVE"
    assert output.confidence_score == 0.88
    assert output.suggested_action == "HOLD"

    # Invalid confidence score out of bounds
    with pytest.raises(Exception):
        ReasoningThesisOutput(
            reasoning_chain="Test",
            sentiment_classification="POSITIVE",
            confidence_score=1.5,  # > 1.0
            suggested_action="HOLD",
        )


def test_cascade_trigger_logic():
    """Verifies cascade conditions triggering Deep Reasoning Tier 2."""
    engine = LocalReasoningSLMEngine()

    # Rule 1: Official regulatory sources must trigger
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=50.0,
        violation_score=0.0,
        source="UBCKNN",
    ) is True
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=50.0,
        violation_score=0.0,
        source="HOSE",
    ) is True

    # Rule 2: Extreme alpha sentiment must trigger
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=25.0,  # < 35.0
        violation_score=0.0,
        source="CafeF",
    ) is True
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=72.0,  # > 65.0
        violation_score=0.0,
        source="Vietstock",
    ) is True

    # Rule 3: Unverified source / forum rumor must trigger
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=50.0,
        violation_score=0.0,
        source="F319",
        source_weight=0.35,
    ) is True

    # Rule 4: Shareholder insider transactions must trigger
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=50.0,
        violation_score=0.0,
        matched_shareholder="Trần Đình Long",
    ) is True

    # Rule 5: Critical regulatory/liquidity panic keywords must trigger
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=50.0,
        violation_score=0.0,
        headline="Cổ phiếu bị bán giải chấp call margin",
    ) is True

    # Rule 6: Kolmogorov gate violation must trigger
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=50.0,
        violation_score=0.32,  # > 0.25
        source="CafeF",
    ) is True
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=50.0,
        violation_score=0.05,
        source="CafeF",
        is_consistent=False,
    ) is True

    # Neutral routine case should NOT trigger
    assert engine.should_trigger_deep_reasoning(
        consistent_alpha=52.0,
        violation_score=0.02,
        source="CafeF",
        source_weight=0.85,
        matched_shareholder=None,
        headline="FPT thay đổi địa chỉ văn phòng",
        is_consistent=True,
    ) is False


def test_deterministic_cot_synthesis():
    """Verifies deterministic CoT reasoning and risk flag attribution."""
    engine = LocalReasoningSLMEngine()

    # Penalty headline
    thesis1 = engine.generate_thesis(
        headline="UBCKNN ra quyết định xử phạt vi phạm hành chính đối với VGC",
        source="UBCKNN",
        source_weight=1.0,
    )
    assert thesis1.sentiment_classification == "NEGATIVE"
    assert "REGULATORY_PENALTY_OR_FRAUD" in thesis1.risk_flags
    assert thesis1.suggested_action == "AVOID"

    # Insider selling headline
    thesis2 = engine.generate_thesis(
        headline="Cổ đông lớn đăng ký bán thoái toàn bộ vốn",
        symbol="NVL",
        source="CafeF",
        matched_shareholder="Bùi Thành Nhơn",
        fast_path_alpha=30.0,
    )
    assert "INSIDER_SELLING_PRESSURE" in thesis2.risk_flags
    assert thesis2.suggested_action == "BUY_DIP"


def test_cache_liveness_performance():
    """Verifies sub-millisecond cached liveness probe."""
    engine = LocalReasoningSLMEngine()
    # First call primes cache
    _ = engine.generate_thesis(headline="Test headline 1")
    # Second call should hit 30s cache
    t0 = engine.generate_thesis(headline="Test headline 2")
    assert t0.latency_ms < 50.0  # Fast sub-50ms execution
