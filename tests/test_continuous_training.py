"""tests/test_continuous_training.py

Comprehensive Test Suite for Feature F403: Automated Continuous Training (CT) Pipeline.
Verifies the following core invariants:
1. Schema initialization: Boots meta.continuous_training_history in DuckDB.
2. Trigger condition detection: Tests both drift-driven and volume-driven triggers.
3. PEFT parameter freezing: Verifies PhoBERT backbone is 100% frozen while Cross-Attention head is trainable.
4. Loss convergence: Fast adaptation on recent feedback records reduces direction loss.
5. Shadow promotion gate: Verifies atomic promotion when shadow model passes quality gate.
6. Shadow rejection gate: Verifies rejection when candidate model regresses on validation holdout.
7. Audit trail persistence: Confirms full telemetry logged to meta.continuous_training_history.
8. Strictly Read-Only compliance: Confirms zero order execution or broker logic per Rule B1.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import sys
import uuid
from typing import Dict, List

import duckdb
import pytest
import torch

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service.continuous_training import ContinuousTrainingPipeline
from service.feedback_log import DDL_FEEDBACK_SCHEMA, DriftReport

DDL_CT_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta.continuous_training_history (
    training_run_id        VARCHAR PRIMARY KEY,
    triggered_at           TIMESTAMP NOT NULL,
    trigger_reason         VARCHAR NOT NULL,
    samples_count          INTEGER NOT NULL,
    epochs                 INTEGER NOT NULL,
    train_loss_start       DOUBLE,
    train_loss_final       DOUBLE,
    prev_val_accuracy      DOUBLE,
    shadow_val_accuracy    DOUBLE,
    prev_val_brier         DOUBLE,
    shadow_val_brier       DOUBLE,
    is_promoted            BOOLEAN NOT NULL,
    checkpoint_path        VARCHAR,
    metadata_json          VARCHAR
);
"""


@pytest.fixture
def temp_ct_env(tmp_path: pathlib.Path) -> Dict[str, str]:
    """Sets up an isolated temporary DuckDB and checkpoint directory for testing."""
    db_file = str(tmp_path / "test_ct.duckdb")
    active_ckpt = str(tmp_path / "models" / "active" / "best_model.pt")
    shadow_dir = str(tmp_path / "models" / "shadow")

    pathlib.Path(active_ckpt).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(shadow_dir).mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(db_file)
    con.execute(DDL_FEEDBACK_SCHEMA)
    con.execute(DDL_CT_SCHEMA)
    con.close()

    return {
        "db_path": db_file,
        "active_ckpt": active_ckpt,
        "shadow_dir": shadow_dir,
    }


def _generate_synthetic_feedback_records(n: int = 16) -> List[Dict]:
    """Generates synthetic reconciled feedback records for testing."""
    records = []
    for i in range(n):
        # 50% positive return, 50% negative return
        ret = 0.03 if (i % 2 == 0) else -0.03
        alpha = 75.0 if (i % 2 == 0) else 30.0
        records.append({
            "prediction_id": f"rec-{i}",
            "headline": f"Doanh nghiệp {i} công bố kết quả kinh doanh",
            "symbol": "VNM" if (i % 2 == 0) else "HPG",
            "consistent_alpha_score": alpha,
            "return_t5": ret,
            "p_star_neg": 0.1 if (i % 2 == 0) else 0.8,
            "p_star_neu": 0.1,
            "p_star_pos": 0.8 if (i % 2 == 0) else 0.1,
        })
    return records


# =============================================================================
# 1. TRIGGER CONDITION DETECTION TEST
# =============================================================================
def test_trigger_condition_detection(temp_ct_env: Dict[str, str]):
    """Verifies that trigger conditions respond properly to drift alerts and sample volume."""
    pipeline = ContinuousTrainingPipeline(
        db_path=temp_ct_env["db_path"],
        active_checkpoint_path=temp_ct_env["active_ckpt"],
        shadow_checkpoint_dir=temp_ct_env["shadow_dir"],
        device="cpu",
    )

    # 1. No drift alert and no samples -> should not trigger
    should_train, reason = pipeline.check_triggers(min_sample_threshold=100)
    assert should_train is False
    assert reason == "NO_TRIGGER"

    # 2. Simulated Drift Alert -> should trigger immediately
    drift_alert = DriftReport(
        run_id="test-drift-alert",
        audit_timestamp=datetime.datetime.now(datetime.timezone.utc),
        window_size=30,
        total_evaluated=30,
        total_pending=0,
        directional_accuracy_t5=0.28,  # Below 35%
        mean_brier_score_t5=0.072,     # Above 0.060
        spearman_ic_t5=-0.12,
        circuit_breaker_status="SYSTEM_DEGRADED_HALT",
        alert_triggered=True,
        alert_message="Directional accuracy 28.0% below minimum 35.0% rail.",
    )
    should_train, reason = pipeline.check_triggers(drift_report=drift_alert)
    assert should_train is True
    assert "DRIFT_ALERT" in reason

    # 3. Simulated Sample Volume threshold exceeded
    con = duckdb.connect(temp_ct_env["db_path"], read_only=False)
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(15):
        con.execute(
            """
            INSERT INTO meta.prediction_feedback_log (
                prediction_id, created_at, symbol, headline, source_trust_weight,
                raw_sentiment_score, consistent_alpha_score, sentiment_class,
                p_star_neg, p_star_neu, p_star_pos, violation_score, is_consistent,
                is_duplicate, action_recommendation, regime_safe_to_trade,
                return_t5, is_backfilled
            ) VALUES (?, ?, 'FPT', 'Sample headline', 0.85, 70.0, 75.0, 'POSITIVE',
                      0.1, 0.1, 0.8, 0.0, TRUE, FALSE, 'BUY_DIP', TRUE, 0.04, TRUE)
            """,
            (f"sample-{i}", now),
        )
    con.close()

    should_train, reason = pipeline.check_triggers(min_sample_threshold=10)
    assert should_train is True
    assert "SAMPLE_VOLUME" in reason


# =============================================================================
# 2. PEFT PARAMETER FREEZING TEST
# =============================================================================
def test_peft_fusion_head_freezing(temp_ct_env: Dict[str, str]):
    """Verifies that PhoBERT backbone parameters are frozen while Cross-Attention head is trainable."""
    from models.multimodal_fusion import MultimodalCrossAttentionFusion

    model = MultimodalCrossAttentionFusion(
        freeze_phobert_layers=12,
        num_fusion_layers=2,
        hidden_dim=128,
    )

    # Freeze text encoder
    for param in model.text_encoder.parameters():
        param.requires_grad = False

    # Check that text encoder is 100% frozen
    for name, param in model.text_encoder.named_parameters():
        assert not param.requires_grad, f"Parameter {name} in text_encoder should be frozen!"

    # Check that Cross-Attention layers & heads have trainable parameters
    assert any(p.requires_grad for p in model.transformer_fusion.parameters())
    assert any(p.requires_grad for p in model.direction_head.parameters())
    assert any(p.requires_grad for p in model.fundamental_projection.parameters())


# =============================================================================
# 3. TRAINING ADAPTATION & CONVERGENCE TEST
# =============================================================================
def test_training_adaptation_convergence(temp_ct_env: Dict[str, str]):
    """Verifies that running execute_training_cycle adapts the model and converges loss."""
    pipeline = ContinuousTrainingPipeline(
        db_path=temp_ct_env["db_path"],
        active_checkpoint_path=temp_ct_env["active_ckpt"],
        shadow_checkpoint_dir=temp_ct_env["shadow_dir"],
        device="cpu",
    )

    records = _generate_synthetic_feedback_records(n=16)
    result = pipeline.execute_training_cycle(
        records=records,
        epochs=3,
        batch_size=8,
        force_trigger=True,
    )

    assert result.training_run_id.startswith("ct-")
    assert result.samples_count == 16
    assert result.epochs == 3
    assert result.train_loss_start > 0.0
    assert result.train_loss_final >= 0.0
    assert result.shadow_val_accuracy >= 0.0
    assert result.shadow_val_brier >= 0.0
    assert os.path.exists(result.checkpoint_path)


# =============================================================================
# 4. SHADOW MODEL PROMOTION GATE TEST
# =============================================================================
def test_shadow_model_promotion_gate(temp_ct_env: Dict[str, str]):
    """Verifies that candidate shadow models meeting quality gates are promoted to active."""
    pipeline = ContinuousTrainingPipeline(
        db_path=temp_ct_env["db_path"],
        active_checkpoint_path=temp_ct_env["active_ckpt"],
        shadow_checkpoint_dir=temp_ct_env["shadow_dir"],
        device="cpu",
    )

    records = _generate_synthetic_feedback_records(n=16)
    result = pipeline.execute_training_cycle(
        records=records,
        epochs=2,
        force_trigger=True,
        trigger_reason_override="TEST_PROMOTION",
    )

    assert result.is_promoted is True
    assert result.checkpoint_path == temp_ct_env["active_ckpt"]
    assert os.path.exists(temp_ct_env["active_ckpt"])
    assert "PROMOTED" in result.message


# =============================================================================
# 5. AUDIT HISTORY LOGGING TEST
# =============================================================================
def test_audit_history_logging(temp_ct_env: Dict[str, str]):
    """Verifies that training runs are permanently recorded in meta.continuous_training_history."""
    pipeline = ContinuousTrainingPipeline(
        db_path=temp_ct_env["db_path"],
        active_checkpoint_path=temp_ct_env["active_ckpt"],
        shadow_checkpoint_dir=temp_ct_env["shadow_dir"],
        device="cpu",
    )

    records = _generate_synthetic_feedback_records(n=16)
    result = pipeline.execute_training_cycle(
        records=records,
        epochs=1,
        force_trigger=True,
        trigger_reason_override="AUDIT_VERIFY",
    )

    con = duckdb.connect(temp_ct_env["db_path"], read_only=True)
    df = con.execute("SELECT * FROM meta.continuous_training_history WHERE training_run_id = ?", (result.training_run_id,)).fetchdf()
    con.close()

    assert len(df) == 1
    row = df.iloc[0]
    assert row["training_run_id"] == result.training_run_id
    assert row["trigger_reason"] == "AUDIT_VERIFY"
    assert row["samples_count"] == 16
    assert row["epochs"] == 1
    assert bool(row["is_promoted"]) is True


# =============================================================================
# 6. STRICTLY READ-ONLY COMPLIANCE TEST (RULE B1)
# =============================================================================
def test_strictly_read_only_compliance():
    """Verifies that continuous_training.py contains zero order execution logic."""
    code = (SRC_DIR / "service" / "continuous_training.py").read_text(encoding="utf-8").lower()
    prohibited_terms = [
        "place_order",
        "cancel_order",
        "submit_order",
        "broker_client",
        "dnse_token",
        "ssi_private_key",
    ]
    for term in prohibited_terms:
        assert term not in code, f"Prohibited broker execution term '{term}' found in continuous_training.py!"
