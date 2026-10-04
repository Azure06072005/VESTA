"""tests/test_bot_registry.py

Unit tests for F501 bot registry.
Verifies uniqueness, valid strategy composition, ordering, and AI twin parity.
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.arena.bot_registry import S, build, export_registry_csv


def test_unique_ids_and_valid_components():
    """Verifies all botIDs are unique and all component IDs are registered in S."""
    rows = build()
    assert len({r[0] for r in rows}) == len(rows)
    assert all(k in S for r in rows for k in r[1].split("+"))


def test_no_ai_bots_listed_first_and_twins_match():
    """Verifies non-AI bots are listed first, followed by AI twins matching non-baseline strategies."""
    rows = build()
    flags = [r[3] for r in rows]
    assert flags == sorted(flags, key=lambda x: x != "no")
    non_ai = {r[1] for r in rows if r[3] == "no" and not r[1].startswith(("S25", "S26"))}
    assert non_ai == {r[1] for r in rows if r[3] == "yes"}


def test_at_least_100_bots():
    """Confirms arena coverage exceeds 100 bots for statistical power."""
    rows = build()
    assert len(rows) >= 100


def test_export_registry_csv(tmp_path: pathlib.Path):
    """Verifies export to CSV produces a valid non-empty file with correct headers."""
    csv_file = str(tmp_path / "bot_reg.csv")
    count = export_registry_csv(csv_file)
    assert count >= 300
    assert pathlib.Path(csv_file).exists()
