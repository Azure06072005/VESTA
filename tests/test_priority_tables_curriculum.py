"""tests/test_priority_tables_curriculum.py

Verification tests for Curriculum Training across Priority Tables 1st -> 4th.
"""
import json
import pathlib
import pytest
import torch

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "out" / "models" / "multimodal_fusion" / "curriculum_training_report.json"
CHECKPOINTS_DIR = REPO_ROOT / "out" / "models" / "multimodal_fusion"


def test_curriculum_report_structure():
    """Validates that curriculum report exists and has all 5 stages."""
    assert REPORT_PATH.exists(), f"Missing report: {REPORT_PATH}"
    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "stages" in data
    stages = data["stages"]
    expected_stages = [
        "Baseline_24_Features",
        "1st_Priority_Market_Foreign_Flow",
        "2nd_Priority_Corporate_Events",
        "3rd_Priority_Market_Breadth_MHI",
        "4th_Priority_Company_Shareholders_Final",
    ]
    for s in expected_stages:
        assert s in stages, f"Missing stage {s} in report"
        assert stages[s]["num_features"] >= 24
        assert "val_direction_accuracy" in stages[s]
        assert "history" in stages[s]


def test_all_checkpoints_exist_and_loadable():
    """Validates that all stage checkpoints exist on disk and have correct feature counts."""
    expected_ckpts = [
        ("checkpoint_stage0_baseline.pt", 24),
        ("checkpoint_stage1_foreign_flow.pt", 27),
        ("checkpoint_stage2_corporate_events.pt", 28),
        ("checkpoint_stage3_market_breadth.pt", 30),
        ("checkpoint_stage4_shareholders_final.pt", 32),
    ]

    for fname, expected_features in expected_ckpts:
        p = CHECKPOINTS_DIR / fname
        assert p.exists(), f"Missing checkpoint: {p}"
        state = torch.load(p, map_location="cpu", weights_only=False)
        assert state["num_fundamental_features"] == expected_features
        assert len(state["feature_columns"]) == expected_features
        assert "model_state_dict" in state
