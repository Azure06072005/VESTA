"""F006 verification.

normalize_events/write_events are pure/DB-only and tested here without
network access. fetch_raw() (the live vnstock call) is NOT covered --
this sandbox cannot reach vnstock's API domain. Fixtures below match the
real columns confirmed live 2026-08-13 (paste of actual discovery script
output): id, category (closed set), display_date1, plus assorted
event-type-specific columns preserved in detail_json.
"""
from __future__ import annotations

import json
import sys
import pathlib

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from etl import db
from etl.retry_failed_jobs import EmptyResultError  # noqa: E402
from crawlers import corporate_events  # noqa: E402


def _sample_events_df() -> pd.DataFrame:
    # Confirmed live shape 2026-08-13 (real pasted output for FPT).
    return pd.DataFrame(
        {
            "id": ["69e6c30a9a7ad2360023b0c1", "6a445e54279ac17a86e4cab3"],
            "event_name_en": ["Cash Dividend", "Annual General Meeting"],
            "category": ["DIVIDEND", "SHAREHOLDER_MEETING"],
            "display_date1": ["2025-06-12T00:00:00", "2025-04-15T00:00:00"],
            "value_per_share": [1000.0, float("nan")],
        }
    )


def test_normalize_events_maps_columns_and_adds_symbol():
    out = corporate_events.normalize_events(_sample_events_df(), "FPT")
    assert list(out.columns) == corporate_events.EVENT_COLUMNS
    assert (out["symbol"] == "FPT").all()
    assert len(out) == 2


def test_normalize_events_uses_category_as_event_type():
    out = corporate_events.normalize_events(_sample_events_df(), "FPT")
    assert set(out["event_type"]) == {"DIVIDEND", "SHAREHOLDER_MEETING"}


def test_normalize_events_known_types_produce_no_log(capsys):
    # Both categories in the fixture are in KNOWN_EVENT_TYPES -- confirmed
    # live 2026-08-13 -- so nothing should be logged as unrecognized.
    corporate_events.normalize_events(_sample_events_df(), "FPT")
    captured = capsys.readouterr()
    assert "unrecognized event_type" not in captured.out


def test_normalize_events_logs_genuinely_unrecognized_type(capsys):
    novel = _sample_events_df().copy()
    novel.loc[0, "category"] = "SOME_NEW_CATEGORY_NOT_YET_SEEN"
    out = corporate_events.normalize_events(novel, "FPT")
    captured = capsys.readouterr()
    assert "unrecognized event_type" in captured.out
    assert "SOME_NEW_CATEGORY_NOT_YET_SEEN" in captured.out
    assert len(out) == 2  # logged, not dropped


def test_normalize_events_preserves_full_row_as_json():
    out = corporate_events.normalize_events(_sample_events_df(), "FPT")
    parsed = json.loads(out.iloc[0]["detail_json"])
    assert parsed["event_name_en"] == "Cash Dividend"
    assert parsed["value_per_share"] == 1000.0


def test_normalize_events_raises_clearly_on_missing_id_column():
    drifted = _sample_events_df().drop(columns=["id"])
    with pytest.raises(ValueError, match="Could not find a source column for 'event_id'"):
        corporate_events.normalize_events(drifted, "FPT")


def test_normalize_events_rejects_empty_fetch():
    with pytest.raises(EmptyResultError):
        corporate_events.normalize_events(pd.DataFrame(), "FPT")


def test_normalize_events_raises_on_duplicate_event_id():
    dupe = pd.concat([_sample_events_df().iloc[[0]], _sample_events_df().iloc[[0]]])
    with pytest.raises(ValueError, match="duplicate"):
        corporate_events.normalize_events(dupe, "FPT")


def test_write_events_is_idempotent(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    normalized = corporate_events.normalize_events(_sample_events_df(), "FPT")

    n1 = corporate_events.write_events(normalized, con)
    n2 = corporate_events.write_events(normalized, con)  # re-run, same input
    assert n1 == n2 == 2

    row_count = con.execute(
        "SELECT COUNT(*) FROM core.corporate_events WHERE symbol = 'FPT'"
    ).fetchone()[0]
    assert row_count == 2  # not doubled


def test_write_events_rejects_schema_mismatch(tmp_path):
    db_path = tmp_path / "test_vesta.duckdb"
    con = db.bootstrap_schema(db_path)
    bad_df = pd.DataFrame({"symbol": ["FPT"]})
    with pytest.raises(ValueError, match="missing columns"):
        corporate_events.write_events(bad_df, con)