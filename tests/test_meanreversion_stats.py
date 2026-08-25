"""F201 verification.

Per the recommendation adopted 2026-08-25: real news volume in this repo
is currently too thin (single-digit to low-double-digit events) for a
real statistical test to mean anything, so this test suite proves the
STATISTICAL LOGIC is correct using synthetic, well-powered fixtures with
an engineered effect -- not real crawled data. A real-data run remains
available via `python -m pipeline.backtest_meanreversion` (no --dry-run)
once enough real news accumulates; that run's report must always be read
with its own n, never assumed significant just because this test suite
passes.

Tests covered:
- sentiment_lexicon: positive/negative/neutral classification, accent-
  insensitivity, mixed-sentiment netting.
- backtest_meanreversion: paired t-test correctly detects an engineered
  reversion effect and correctly detects NO effect in a null-effect
  fixture (both are needed -- a test suite that can only detect "yes"
  can't be trusted to also say "no").
- InsufficientSampleError / insufficient_data status: a small-n group is
  never silently scored as if it had statistical power.
- Reproducibility: identical input produces bit-identical JSON report on
  a second run (conventions.md's backtest reproducibility rule).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pipeline.sentiment_lexicon import classify_headline, score_headline  # noqa: E402
from pipeline import backtest_meanreversion as bmr  # noqa: E402


# ---------------------------------------------------------------------------
# sentiment_lexicon.py
# ---------------------------------------------------------------------------

def test_positive_headline_scores_positive():
    assert score_headline("FPT bao lai rong tang manh trong quy 2") > 0
    assert classify_headline("FPT bao lai rong tang manh trong quy 2") == "positive"


def test_negative_headline_scores_negative():
    assert score_headline("Cong ty bao lo rong, no xau tang cao") < 0
    assert classify_headline("Cong ty bao lo rong, no xau tang cao") == "negative"


def test_neutral_headline_with_no_lexicon_hits():
    assert score_headline("Doanh nghiep to chuc hoi thao thuong nien") == 0.0
    assert classify_headline("Doanh nghiep to chuc hoi thao thuong nien") == "neutral"


def test_empty_headline_is_neutral():
    assert score_headline("") == 0.0
    assert classify_headline(None or "") == "neutral"


def test_accent_insensitive_matching():
    """Real headlines mix accented/unaccented Vietnamese (see F003 vs F004
    sample headlines already in the repo) -- both must match."""
    accented = score_headline("Công ty báo lỗ ròng trong quý này")
    unaccented = score_headline("Cong ty bao lo rong trong quy nay")
    assert accented < 0
    assert unaccented < 0


def test_mixed_sentiment_nets_out_not_forced_to_one_class():
    """A headline with both a positive and negative term should net
    toward zero, not be arbitrarily forced positive or negative."""
    mixed = "Loi nhuan tang nhung cong ty van bi xu phat vi vi pham"
    score = score_headline(mixed)
    assert -1.0 < score < 1.0  # netted, not maxed out either direction


# ---------------------------------------------------------------------------
# backtest_meanreversion.py -- synthetic fixtures
# ---------------------------------------------------------------------------

def _make_synthetic_events(
    n_negative: int,
    n_positive: int,
    n_neutral: int,
    reversion_effect: bool,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a synthetic core.pit_events-shaped DataFrame.

    reversion_effect=True: negative-sentiment events get an engineered
    dip-then-revert pattern (return_t5 strongly negative, return_t30 much
    less negative) so the paired t-test SHOULD find a significant effect.

    reversion_effect=False: negative-sentiment events get symmetric random
    noise around the same mean at t5 and t30 (no engineered reversion) so
    the paired t-test SHOULD NOT find a significant effect -- this is the
    null-effect control fixture.
    """
    rng = np.random.default_rng(seed)
    rows = []
    base_price = 100.0
    base_date = dt.datetime(2024, 6, 1)

    neg_headlines = ["Cong ty bao lo rong trong quy nay"] * n_negative
    pos_headlines = ["FPT bao lai rong tang manh"] * n_positive
    neu_headlines = ["Doanh nghiep to chuc hoi thao"] * n_neutral

    idx = 0
    for i, headline in enumerate(neg_headlines):
        if reversion_effect:
            r5 = -0.05 + rng.normal(0, 0.005)
            r30 = -0.01 + rng.normal(0, 0.005)  # reverted most of the dip
        else:
            r5 = rng.normal(-0.02, 0.01)
            r30 = rng.normal(-0.02, 0.01)  # same mean, no reversion
        price5 = base_price * (1 + r5)
        price30 = base_price * (1 + r30)
        rows.append(
            {
                "symbol": "FPT",
                "source_url": f"https://example.com/neg-{i}",
                "published_at": base_date + dt.timedelta(days=i),
                "headline": headline,
                "price_at_publish": base_price,
                "price_t1": base_price,
                "price_t5": price5,
                "price_t30": price30,
            }
        )
        idx += 1

    for i, headline in enumerate(pos_headlines):
        rows.append(
            {
                "symbol": "FPT",
                "source_url": f"https://example.com/pos-{i}",
                "published_at": base_date + dt.timedelta(days=idx + i),
                "headline": headline,
                "price_at_publish": base_price,
                "price_t1": base_price,
                "price_t5": base_price * (1 + rng.normal(0.03, 0.01)),
                "price_t30": base_price * (1 + rng.normal(0.04, 0.01)),
            }
        )

    for i, headline in enumerate(neu_headlines):
        rows.append(
            {
                "symbol": "FPT",
                "source_url": f"https://example.com/neu-{i}",
                "published_at": base_date + dt.timedelta(days=idx + len(pos_headlines) + i),
                "headline": headline,
                "price_at_publish": base_price,
                "price_t1": base_price,
                "price_t5": base_price * (1 + rng.normal(0.0, 0.01)),
                "price_t30": base_price * (1 + rng.normal(0.0, 0.01)),
            }
        )

    return pd.DataFrame(rows)


def test_engineered_reversion_effect_is_detected():
    """With a real engineered dip-then-revert pattern and n well above
    MIN_SAMPLE_SIZE, the paired t-test must find a significant effect
    (p < 0.05) in the correct direction (mean_return_t30 > mean_return_t5)."""
    df = _make_synthetic_events(
        n_negative=40, n_positive=10, n_neutral=10, reversion_effect=True
    )
    report = bmr.run_backtest(df)

    neg_result = report["overall"]["negative_sentiment_group"]
    assert neg_result["status"] == "ok"
    assert neg_result["n"] == 40
    assert neg_result["p_value"] < 0.05
    assert neg_result["mean_return_t30"] > neg_result["mean_return_t5"]


def test_null_effect_fixture_does_not_falsely_detect_reversion():
    """With no engineered reversion (same mean at t5 and t30), the test
    must NOT report a significant effect -- a test suite that only ever
    finds 'yes' cannot be trusted."""
    df = _make_synthetic_events(
        n_negative=40, n_positive=10, n_neutral=10, reversion_effect=False
    )
    report = bmr.run_backtest(df)

    neg_result = report["overall"]["negative_sentiment_group"]
    assert neg_result["status"] == "ok"
    assert neg_result["n"] == 40
    assert neg_result["p_value"] > 0.05


def test_small_sample_is_flagged_insufficient_not_silently_tested():
    """Fewer than MIN_SAMPLE_SIZE negative-sentiment events must produce
    status='insufficient_data', never a p-value computed on too few
    points -- this is the honesty guard for the real thin-news-sample
    situation this repo is actually in right now."""
    df = _make_synthetic_events(
        n_negative=3, n_positive=2, n_neutral=2, reversion_effect=True
    )
    report = bmr.run_backtest(df)

    neg_result = report["overall"]["negative_sentiment_group"]
    assert neg_result["status"] == "insufficient_data"
    assert neg_result["p_value"] is None
    assert neg_result["n"] == 3


def test_empty_input_does_not_crash_and_reports_zero_events():
    """dry-run / no-data case (verification.md's smoke-run mode) must
    produce a valid report structure, not raise."""
    empty = pd.DataFrame(
        columns=[
            "symbol", "source_url", "published_at", "headline",
            "price_at_publish", "price_t1", "price_t5", "price_t30",
        ]
    )
    report = bmr.run_backtest(empty)
    assert report["total_events_loaded"] == 0
    assert report["overall"]["negative_sentiment_group"]["status"] == "insufficient_data"


def test_rows_with_null_future_price_are_excluded_not_imputed():
    """A row with NULL price_t30 (insufficient future OHLCV per F102's
    own convention) must be dropped from the t30 statistic, never
    imputed as zero return."""
    df = _make_synthetic_events(
        n_negative=15, n_positive=0, n_neutral=0, reversion_effect=True
    )
    # Null out price_t30 for half the negative rows.
    df.loc[df.index[:7], "price_t30"] = None

    scored = bmr.score_events(df)
    valid_t30 = scored.dropna(subset=["return_t30"])
    assert len(valid_t30) == 8  # 15 - 7 nulled out


def test_regime_assignment():
    assert bmr.assign_regime(dt.datetime(2020, 6, 1)) == "2020_covid_crash_recovery"
    assert bmr.assign_regime(dt.datetime(2022, 3, 15)) == "2022_realestate_bond_crisis"
    assert bmr.assign_regime(dt.datetime(2024, 1, 1)) == "2023_2024_recovery"


def test_per_regime_report_present_for_every_declared_regime():
    df = _make_synthetic_events(
        n_negative=40, n_positive=10, n_neutral=10, reversion_effect=True
    )
    report = bmr.run_backtest(df)
    regime_names = {name for name, _, _ in bmr.REGIME_BOUNDARIES}
    assert set(report["per_regime_negative_sentiment"].keys()) == regime_names


# ---------------------------------------------------------------------------
# Reproducibility (conventions.md: bit-identical output on re-run)
# ---------------------------------------------------------------------------

def test_report_is_bit_identical_on_rerun_same_input(tmp_path):
    df = _make_synthetic_events(
        n_negative=40, n_positive=10, n_neutral=10, reversion_effect=True, seed=7
    )

    out1 = tmp_path / "report1.json"
    out2 = tmp_path / "report2.json"

    report1 = bmr.run_backtest(df)
    report2 = bmr.run_backtest(df)
    bmr.write_report(report1, out1)
    bmr.write_report(report2, out2)

    assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


def test_report_json_is_valid_and_sorted():
    df = _make_synthetic_events(
        n_negative=15, n_positive=5, n_neutral=5, reversion_effect=True
    )
    report = bmr.run_backtest(df)
    serialized = json.dumps(report, sort_keys=True, ensure_ascii=False)
    reparsed = json.loads(serialized)
    assert reparsed["total_events_loaded"] == 25


def test_run_dry_run_mode_produces_valid_report(tmp_path):
    out_path = tmp_path / "smoke_report.json"
    report = bmr.run(report_path=str(out_path), dry_run=True)
    assert out_path.exists()
    assert report["total_events_loaded"] == 0
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["total_events_loaded"] == 0