"""F201: PROOF -- sentiment mean-reversion backtest on core.pit_events.

Hypothesis (per DECISIONS.md project goal): after a negative-sentiment news
event, price dips by t+5 and partially reverts by t+30. Tested with a
paired t-test on (return_t5, return_t30) for the negative-sentiment group,
where "reversion" means return_t30 is significantly less negative (closer
to zero, or positive) than return_t5.

SENTIMENT SOURCE: src/pipeline/sentiment_lexicon.py (rule-based, hand-built,
explicitly a STATED ASSUMPTION -- see that module's docstring). F201 is
scoped to the cheap rule-based scorer per DECISIONS.md's sequencing
decision (2026-08-09): a fine-tuned SLM (F301) is not justified unless this
cheap scorer already shows a real effect.

SAMPLE SIZE HONESTY (per B3 and the 2026-08-25 F201 scoping discussion):
this repo's real news volume is structurally thin -- F003 returns ~50 most
recent articles/symbol with no backfill, F004 is page-1-only (~28
items/run), and neither can be backfilled retroactively (see DECISIONS.md
2026-08-16 item 8). A pilot-universe run may have single-digit-to-low-
double-digit event counts in the negative-sentiment bucket. This module
NEVER hides or rounds away a small n: the report always includes n, and
`run_backtest` raises InsufficientSampleError (not a silently-empty report)
if n falls below MIN_SAMPLE_SIZE for the requested regime split, so a thin
sample cannot be mistaken for "the test ran and found nothing."

REGIME SPLITTING: DECISIONS.md (2026-08-16, item 8) documents that VN
market regimes (2018 correction, 2020 COVID, 2022 real-estate/bond crisis,
2023-24 recovery) are historically distinct enough that a backtest
confined to one regime risks looking robust while being regime-specific.
Per-regime reporting is implemented (`REGIME_BOUNDARIES`), but with today's
thin real sample most regimes will have too few events to test
independently -- the report marks regimes below MIN_SAMPLE_SIZE as
"insufficient_data" rather than computing a statistic on too few points.

REPRODUCIBILITY (conventions.md: "tests for reproducibility, not just runs
without error"): `run_backtest` is a pure function of its input DataFrame
-- no randomness, no wall-clock-dependent behavior -- so identical input
produces bit-identical JSON output on every re-run. The CLI entry point
writes symbol/order-independent output (event rows are sorted before any
aggregation) for the same reason.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import math
from dataclasses import dataclass

import duckdb
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from pipeline.sentiment_lexicon import score_headline  # noqa: E402

# Below this event count in a group, no statistic is computed for that
# group -- a p-value from n<MIN_SAMPLE_SIZE is not evidence of anything
# and reporting one anyway would misrepresent statistical power.
# STATED ASSUMPTION: 10 is a conventional statistical floor (rule-of-thumb
# minimum for a paired t-test to be minimally meaningful), not derived
# from a power analysis specific to this dataset's effect-size target --
# revisit with a real power calculation once F301 needs a stricter bar.
MIN_SAMPLE_SIZE = 10

# Headlines scoring in (-neutral_band, +neutral_band) are excluded from
# both the positive and negative groups entirely (not lumped into either) --
# the hypothesis is specifically about NEGATIVE sentiment reversion, so a
# genuinely neutral/no-lexicon-hit headline is not informative either way.
NEUTRAL_BAND = 0.0

# Regime boundaries per DECISIONS.md 2026-08-16 item 8. End-exclusive.
# STATED ASSUMPTION: boundary dates are approximate calendar markers for
# named VN market regimes, not derived from a formal regime-detection
# model -- sourced from the qualitative regime list already agreed in
# DECISIONS.md, not invented fresh here.
REGIME_BOUNDARIES: tuple[tuple[str, dt.date, dt.date], ...] = (
    ("2018_correction", dt.date(2018, 1, 1), dt.date(2019, 1, 1)),
    ("2020_covid_crash_recovery", dt.date(2020, 1, 1), dt.date(2021, 1, 1)),
    ("2022_realestate_bond_crisis", dt.date(2022, 1, 1), dt.date(2023, 1, 1)),
    ("2023_2024_recovery", dt.date(2023, 1, 1), dt.date(2025, 1, 1)),
    ("2025_2026_other", dt.date(2025, 1, 1), dt.date(2027, 1, 1)),
)


class InsufficientSampleError(Exception):
    """Raised when a requested regime/group has fewer than MIN_SAMPLE_SIZE
    events -- signals "not enough data to test", distinct from "tested and
    found no effect"."""


@dataclass
class GroupResult:
    n: int
    mean_return_t5: float | None = None
    mean_return_t30: float | None = None
    t_statistic: float | None = None
    p_value: float | None = None
    cohens_d: float | None = None
    status: str = "ok"  # "ok" | "insufficient_data"


def assign_regime(published_at: dt.datetime) -> str:
    """Map a timestamp to a named regime bucket per REGIME_BOUNDARIES."""
    d = published_at.date() if isinstance(published_at, dt.datetime) else published_at
    for name, start, end in REGIME_BOUNDARIES:
        if start <= d < end:
            return name
    return "unclassified"


def load_events(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load core.pit_events, sorted deterministically for reproducibility.

    Only rows with a non-NULL price_at_publish are usable (return_t5/t30
    cannot be computed without an anchor price) -- rows with NULL
    price_at_publish are dropped here, not treated as zero-return.
    """
    df = con.execute(
        "SELECT symbol, source_url, published_at, headline, "
        "price_at_publish, price_t1, price_t5, price_t30 "
        "FROM core.pit_events "
        "WHERE price_at_publish IS NOT NULL "
        "ORDER BY symbol, published_at, source_url"
    ).df()
    return df


def score_events(df: pd.DataFrame) -> pd.DataFrame:
    """Add sentiment score/class and return_t5/return_t30 columns.

    Returns are simple pct-change from price_at_publish, NOT log returns --
    consistent with this repo not having chosen a return convention
    elsewhere yet (F102 stores raw adjusted prices, not returns). A row
    with NULL price_t5 or price_t30 keeps return_t5/return_t30 as NaN
    (insufficient future OHLCV existed at build time, per F102's own
    NULL-not-fabricated convention) -- it is dropped from any statistic
    that needs that horizon, not imputed.
    """
    out = df.copy()
    out["sentiment_score"] = out["headline"].apply(score_headline)
    out["sentiment_class"] = out["sentiment_score"].apply(
        lambda s: "neutral" if abs(s) <= NEUTRAL_BAND else ("positive" if s > 0 else "negative")
    )
    out["return_t5"] = (out["price_t5"] - out["price_at_publish"]) / out["price_at_publish"]
    out["return_t30"] = (out["price_t30"] - out["price_at_publish"]) / out["price_at_publish"]
    out["regime"] = out["published_at"].apply(assign_regime)
    return out


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    if x > (a + 1.0) / (a + b + 2.0):
        # Symmetry relation: I_x(a, b) = 1.0 - I_{1-x}(b, a)
        return 1.0 - _betai(b, a, 1.0 - x)

    MAXIT, EPS, FPMIN = 200, 3.0e-12, 1.0e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        del_h = d * c
        h *= del_h
        if abs(del_h - 1.0) < EPS:
            break

    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    return float(bt * h / a)


def _compute_two_tailed_p_value(t_stat: float, df: int) -> float:
    """Two-tailed p-value for Student's t-distribution with df degrees of freedom."""
    if df <= 0 or math.isnan(t_stat):
        return float("nan")
    t2 = t_stat * t_stat
    x = df / (df + t2)
    return float(_betai(df / 2.0, 0.5, x))


def _paired_reversion_test(sub: pd.DataFrame) -> GroupResult:
    """Paired t-test: is return_t30 significantly greater (less negative /
    more positive) than return_t5, within the same events? This is the
    literal "did it dip then revert" test -- paired because it's the same
    event's own t5 and t30 outcomes being compared, not two independent
    samples.
    """
    valid = sub.dropna(subset=["return_t5", "return_t30"])
    n = len(valid)
    if n < MIN_SAMPLE_SIZE:
        return GroupResult(n=n, status="insufficient_data")

    diffs = valid["return_t30"] - valid["return_t5"]
    mean_diff = float(diffs.mean())
    std_diff = float(diffs.std(ddof=1)) if len(diffs) > 1 else 0.0

    if std_diff > 0:
        se = std_diff / math.sqrt(n)
        t_stat = mean_diff / se
        p_val = _compute_two_tailed_p_value(t_stat, n - 1)
        d = float(mean_diff / std_diff)
    else:
        t_stat = 0.0
        p_val = 1.0
        d = 0.0

    return GroupResult(
        n=n,
        mean_return_t5=float(valid["return_t5"].mean()),
        mean_return_t30=float(valid["return_t30"].mean()),
        t_statistic=float(t_stat),
        p_value=float(p_val),
        cohens_d=d,
        status="ok",
    )


def run_backtest(events_df: pd.DataFrame) -> dict[str, object]:
    """Pure function: scored events DataFrame -> full report dict.

    Deterministic given identical input (conventions.md reproducibility
    requirement) -- no randomness, no dependence on wall-clock time other
    than what's already baked into the input's `regime` column.
    """
    scored = score_events(events_df)

    negative = scored[scored["sentiment_class"] == "negative"]
    positive = scored[scored["sentiment_class"] == "positive"]
    neutral = scored[scored["sentiment_class"] == "neutral"]

    overall_negative = _paired_reversion_test(negative)
    overall_positive = _paired_reversion_test(positive)

    per_regime: dict[str, dict[str, object]] = {}
    for regime_name, _, _ in REGIME_BOUNDARIES:
        regime_negative = negative[negative["regime"] == regime_name]
        result = _paired_reversion_test(regime_negative)
        per_regime[regime_name] = result.__dict__

    report = {
        "hypothesis": (
            "After negative-sentiment news, price dips by t+5 and "
            "partially reverts by t+30 (paired t-test: return_t30 > "
            "return_t5 within the same events)."
        ),
        "sentiment_source": "rule_based_lexicon (src/pipeline/sentiment_lexicon.py, "
        "stated assumption, not validated against labeled data -- see module docstring)",
        "min_sample_size": MIN_SAMPLE_SIZE,
        "total_events_loaded": int(len(scored)),
        "sentiment_class_counts": {
            "negative": int(len(negative)),
            "positive": int(len(positive)),
            "neutral": int(len(neutral)),
        },
        "overall": {
            "negative_sentiment_group": overall_negative.__dict__,
            "positive_sentiment_group": overall_positive.__dict__,
        },
        "per_regime_negative_sentiment": per_regime,
    }
    return report


def write_report(report: dict[str, object], out_path: pathlib.Path) -> None:
    """Write the report as sorted, deterministic JSON (bit-identical
    output on re-run given identical input, per conventions.md)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def run(report_path: str = "out/meanreversion_report.json", dry_run: bool = False) -> dict[str, object]:
    """Entry point used by both the CLI and verification.md's smoke run.

    dry_run=True (per verification.md's smoke-run row) skips the real DB
    read and runs against an empty DataFrame with the right columns --
    proves the code path executes without requiring a populated database,
    it does NOT produce a meaningful statistical report.
    """
    if dry_run:
        empty = pd.DataFrame(
            columns=[
                "symbol", "source_url", "published_at", "headline",
                "price_at_publish", "price_t1", "price_t5", "price_t30",
            ]
        )
        report = run_backtest(empty)
    else:
        con = db.connect()
        events_df = load_events(con)
        report = run_backtest(events_df)

    write_report(report, pathlib.Path(report_path))
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="F201: sentiment mean-reversion backtest on core.pit_events"
    )
    parser.add_argument("--report", default="out/meanreversion_report.json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run against an empty DataFrame (verification.md smoke-run mode; "
        "proves the code path executes, not that a real effect exists)",
    )
    args = parser.parse_args()

    result = run(report_path=args.report, dry_run=args.dry_run)
    print(f"Report written to {args.report}")
    print(f"total_events_loaded={result['total_events_loaded']}")
    print(f"sentiment_class_counts={result['sentiment_class_counts']}")