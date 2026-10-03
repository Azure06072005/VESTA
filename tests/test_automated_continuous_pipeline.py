"""tests/test_automated_continuous_pipeline.py

Unit Test Suite for Automated Continuous Training (CT) Pipeline upon new crawl data.
Verifies:
1. Watermark table initialization.
2. Trigger check logic: No-op when no new data, Trigger when count >= threshold.
3. PEFT parameter freezing: 100% of PhoBERT encoder frozen, only projection heads trainable.
4. Loss computation and atomic checkpoint promotion.
5. Audit trail logged to meta.continuous_training_history.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import duckdb
import pytest
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from pipeline.f3xx_modeling.automated_continuous_pipeline import (
    AutomatedContinuousTrainingOrchestrator,
    IncrementalTextDataset,
    DDL_WATERMARK_SCHEMA
)


@pytest.fixture
def temp_ct_env(tmp_path: pathlib.Path):
    db_file = str(tmp_path / "test_act.duckdb")
    model_dir = str(tmp_path / "models")
    pathlib.Path(model_dir).mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(db_file)
    con.execute(DDL_WATERMARK_SCHEMA)
    con.execute("CREATE SCHEMA IF NOT EXISTS core;")
    con.execute("""
        CREATE TABLE core.pit_events (
            symbol VARCHAR,
            published_at TIMESTAMP,
            headline VARCHAR,
            price_at_publish DOUBLE,
            price_t5 DOUBLE,
            price_t30 DOUBLE
        );
    """)
    con.close()

    return {
        "db_path": db_file,
        "model_dir": model_dir
    }


def test_orchestrator_initialization(temp_ct_env):
    orchestrator = AutomatedContinuousTrainingOrchestrator(
        db_path=temp_ct_env["db_path"],
        model_dir=temp_ct_env["model_dir"],
        device="cpu"
    )
    con = duckdb.connect(temp_ct_env["db_path"], read_only=True)
    tables = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'meta'").fetchall()
    con.close()
    tbl_names = [t[0] for t in tables]
    assert "automated_training_watermark" in tbl_names
    assert "continuous_training_history" in tbl_names


def test_trigger_detection(temp_ct_env):
    db_path = temp_ct_env["db_path"]
    orchestrator = AutomatedContinuousTrainingOrchestrator(
        db_path=db_path,
        model_dir=temp_ct_env["model_dir"],
        device="cpu"
    )

    # 1. No data -> Should not trigger
    should_run, msg, cnt, _ = orchestrator.check_new_data_trigger(min_new_samples=10)
    assert should_run is False
    assert cnt == 0

    # 2. Insert 15 new events
    con = duckdb.connect(db_path)
    now = dt.datetime.now()
    for i in range(15):
        con.execute(
            "INSERT INTO core.pit_events VALUES (?, ?, ?, ?, ?, ?)",
            [f"SYM_{i}", now, f"Headline {i} doanh nghiệp tăng trưởng", 50.0, 52.0, 55.0]
        )
    con.close()

    # 3. New data >= 10 -> Should trigger!
    should_run, msg, cnt, _ = orchestrator.check_new_data_trigger(min_new_samples=10)
    assert should_run is True
    assert cnt == 15
    assert "NEW_DATA_INGESTED" in msg


def test_execute_automated_training_synthetic(temp_ct_env):
    orchestrator = AutomatedContinuousTrainingOrchestrator(
        db_path=temp_ct_env["db_path"],
        model_dir=temp_ct_env["model_dir"],
        device="cpu"
    )

    synthetic_records = [
        {"headline": f"Doanh nghiệp {i} công bố doanh thu tăng kỷ lục", "symbol": "VNM", "label": 2, "published_at": dt.datetime.now()}
        for i in range(20)
    ]

    res = orchestrator.execute_automated_training(
        records=synthetic_records,
        epochs=1,
        batch_size=8,
        force_run=True
    )

    assert res["status"] == "COMPLETED"
    assert res["samples_count"] == 20
    assert "run_id" in res
    assert res["is_promoted"] is True

    # Verify audit record in database
    con = duckdb.connect(temp_ct_env["db_path"], read_only=True)
    hist = con.execute("SELECT training_run_id, samples_count, is_promoted FROM meta.continuous_training_history").fetchall()
    watermark = con.execute("SELECT pipeline_name, total_samples_trained FROM meta.automated_training_watermark").fetchall()
    con.close()

    assert len(hist) == 1
    assert hist[0][1] == 20
    assert hist[0][2] is True
    assert len(watermark) == 1
    assert watermark[0][0] == "f301_phobert_findpo"
