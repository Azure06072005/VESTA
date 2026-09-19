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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
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


import numpy as np


def score_events_multimodal(
    df: pd.DataFrame,
    model_path: str = "out/models/multimodal_fusion/best_model.pt",
    batch_size: int = 256,
    device_str: str | None = None,
) -> pd.DataFrame:
    """Score events using fine-tuned F302 Multimodal Cross-Attention Fusion model."""
    if len(df) == 0:
        out = df.copy()
        out["sentiment_score"] = []
        out["sentiment_class"] = []
        out["pred_ret_t5"] = []
        out["alpha_score"] = []
        out["return_t5"] = []
        out["return_t30"] = []
        out["regime"] = []
        return out

    import torch
    from torch.utils.data import DataLoader
    from transformers import AutoTokenizer
    from models.multimodal_fusion import MultimodalCrossAttentionFusion, DEFAULT_FUNDAMENTAL_FEATURES
    from models.train_multimodal_fusion import MultimodalFinancialDataset

    out = df.copy()
    if "price_at_publish" not in out.columns and "p0" in out.columns:
        out["price_at_publish"] = out["p0"]
    if "price_t5" not in out.columns and "p5" in out.columns:
        out["price_t5"] = out["p5"]
    if "price_t30" not in out.columns and "p30" in out.columns:
        out["price_t30"] = out["p30"]
    if "published_at" in out.columns:
        out["published_at"] = pd.to_datetime(out["published_at"])
    if "headline" not in out.columns and "headline_clean" in out.columns:
        out["headline"] = out["headline_clean"]

    device = torch.device(device_str if device_str else ("cuda" if torch.cuda.is_available() else "cpu"))
    model = MultimodalCrossAttentionFusion(
        phobert_model_name="vinai/phobert-base-v2",
        freeze_phobert_layers=8,
        num_fundamental_features=len(DEFAULT_FUNDAMENTAL_FEATURES),
        hidden_dim=128,
        num_heads=4,
        num_fusion_layers=2,
    )

    p = pathlib.Path(model_path)
    if not p.exists():
        fallback_p = pathlib.Path("out/models/multimodal_fusion/last_checkpoint.pt")
        if fallback_p.exists():
            p = fallback_p

    if p.exists():
        state = torch.load(p, map_location=device)
        model.load_state_dict(state["model_state_dict"] if "model_state_dict" in state else state)
    
    if device.type == "cuda":
        model = model.half()
    model.to(device)
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base-v2")
    ds = MultimodalFinancialDataset(df=out, tokenizer=tokenizer, max_seq_length=128)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False)

    all_preds_return = []
    all_preds_dir = []
    all_preds_sent = []

    with torch.no_grad():
        for b in loader:
            input_ids = b["input_ids"].to(device)
            attention_mask = b["attention_mask"].to(device)
            fundamentals = b["fundamentals"].to(device)
            if device.type == "cuda":
                fundamentals = fundamentals.half()
            regime_ids = b["regime_id"].to(device)

            m_out = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                fundamentals=fundamentals,
                regime_ids=regime_ids,
            )
            all_preds_return.extend(m_out.return_preds.squeeze(-1).float().cpu().numpy())
            all_preds_dir.extend(m_out.direction_logits.argmax(dim=-1).cpu().numpy())
            all_preds_sent.extend(m_out.sentiment_logits.argmax(dim=-1).cpu().numpy())

    out["pred_ret_t5"] = np.array(all_preds_return, dtype=float)
    out["pred_dir_t5"] = np.array(all_preds_dir, dtype=int)
    out["pred_sent"] = np.array(all_preds_sent, dtype=int)

    sigma_threshold = 0.05
    out["alpha_score"] = 50.0 + 50.0 * np.tanh(out["pred_ret_t5"] / sigma_threshold)
    out["sentiment_score"] = (out["alpha_score"] - 50.0) / 50.0

    out["sentiment_class"] = out["alpha_score"].apply(
        lambda s: "negative" if s < 45.0 else ("positive" if s > 55.0 else "neutral")
    )

    out["return_t5"] = (out["price_t5"] - out["price_at_publish"]) / out["price_at_publish"]
    out["return_t30"] = (out["price_t30"] - out["price_at_publish"]) / out["price_at_publish"]
    out["regime"] = out["published_at"].apply(assign_regime)
    return out


def run_backtest(
    events_df: pd.DataFrame,
    sentiment_source: str = "rule_based",
    model_path: str = "out/models/multimodal_fusion/best_model.pt",
) -> dict[str, object]:
    """Pure function: scored events DataFrame -> full report dict."""
    if sentiment_source == "multimodal":
        scored = score_events_multimodal(events_df, model_path=model_path)
    else:
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

    baseline_cohens_d = 0.0557
    observed_cohens_d = overall_negative.cohens_d
    beats_baseline = (
        bool(observed_cohens_d > baseline_cohens_d)
        if observed_cohens_d is not None
        else False
    )
    improvement_ratio = (
        float(observed_cohens_d / baseline_cohens_d)
        if observed_cohens_d and baseline_cohens_d > 0
        else 0.0
    )

    continuous_alpha_metrics = None
    if sentiment_source == "multimodal" and "alpha_score" in scored.columns and len(scored) > 0:
        sweep_results = {}
        for th in [45, 40, 35, 30, 25, 20]:
            sub_th = scored[scored["alpha_score"] < th]
            res_th = _paired_reversion_test(sub_th)
            sweep_results[f"S_lt_{th}"] = res_th.__dict__
        continuous_alpha_metrics = {
            "mean_alpha_score": float(scored["alpha_score"].mean()),
            "median_alpha_score": float(scored["alpha_score"].median()),
            "std_alpha_score": float(scored["alpha_score"].std()),
            "threshold_sweep": sweep_results,
        }

    report = {
        "hypothesis": (
            "After negative-sentiment news, price dips by t+5 and "
            "partially reverts by t+30 (paired t-test: return_t30 > "
            "return_t5 within the same events)."
        ),
        "sentiment_source": (
            "multimodal_cross_attention_fusion (PhoBERT-base + 24 RankGauss + Macro Regime, F302)"
            if sentiment_source == "multimodal"
            else "rule_based_lexicon (src/pipeline/sentiment_lexicon.py, stated assumption)"
        ),
        "min_sample_size": MIN_SAMPLE_SIZE,
        "total_events_loaded": int(len(scored)),
        "sentiment_class_counts": {
            "negative": int(len(negative)),
            "positive": int(len(positive)),
            "neutral": int(len(neutral)),
        },
        "baseline_f201_cohens_d": baseline_cohens_d,
        "cohens_d": observed_cohens_d,
        "beats_baseline": beats_baseline,
        "effect_size_improvement_ratio": round(improvement_ratio, 4),
        "overall": {
            "negative_sentiment_group": overall_negative.__dict__,
            "positive_sentiment_group": overall_positive.__dict__,
        },
        "per_regime_negative_sentiment": per_regime,
        "continuous_alpha_metrics": continuous_alpha_metrics,
    }
    return report


def write_report(report: dict[str, object], out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def run(
    report_path: str = "out/meanreversion_report.json",
    dry_run: bool = False,
    db_path: str | pathlib.Path | None = None,
    sentiment_source: str = "rule_based",
    dataset_path: str | None = None,
    model_path: str = "out/models/multimodal_fusion/best_model.pt",
) -> dict[str, object]:
    if dry_run:
        empty = pd.DataFrame(
            columns=[
                "symbol", "source_url", "published_at", "headline",
                "price_at_publish", "price_t1", "price_t5", "price_t30",
            ]
        )
        report = run_backtest(empty, sentiment_source=sentiment_source, model_path=model_path)
    elif sentiment_source == "multimodal":
        target_dataset = dataset_path or (
            "data/processed/f104/f104_val.parquet"
            if pathlib.Path("data/processed/f104/f104_val.parquet").exists()
            else None
        )
        if target_dataset and pathlib.Path(target_dataset).exists():
            con = duckdb.connect()
            events_df = con.execute(f"SELECT * FROM '{target_dataset}'").df()
            con.close()
        else:
            target_db = db_path or db.DB_PATH
            con = db.connect(db_path=target_db, read_only=True)
            events_df = load_events(con)
        report = run_backtest(events_df, sentiment_source="multimodal", model_path=model_path)
    else:
        target_db = db_path or db.DB_PATH
        con = db.connect(db_path=target_db, read_only=True)
        events_df = load_events(con)
        report = run_backtest(events_df, sentiment_source="rule_based")

    write_report(report, pathlib.Path(report_path))
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="F201/F303: sentiment mean-reversion backtest on core.pit_events"
    )
    parser.add_argument("--db-path", default="", help="Path to DuckDB database (default: VESTA_DB_PATH)")
    parser.add_argument("--report", default="out/meanreversion_report.json")
    parser.add_argument(
        "--sentiment-source",
        choices=["rule_based", "multimodal"],
        default="rule_based",
        help="Sentiment engine source: rule_based (F201) or multimodal (F303)",
    )
    parser.add_argument("--dataset", default=None, help="Dataset path for multimodal evaluation")
    parser.add_argument("--model-path", default="out/models/multimodal_fusion/best_model.pt", help="Path to multimodal checkpoint")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run against an empty DataFrame (verification.md smoke-run mode)",
    )
    args = parser.parse_args()

    result = run(
        report_path=args.report,
        dry_run=args.dry_run,
        db_path=args.db_path or None,
        sentiment_source=args.sentiment_source,
        dataset_path=args.dataset,
        model_path=args.model_path,
    )
    print(f"Report written to {args.report}")
    print(f"total_events_loaded={result['total_events_loaded']}")
    print(f"sentiment_class_counts={result['sentiment_class_counts']}")
    if "cohens_d" in result and result["cohens_d"] is not None:
        print(f"Cohen's d={result['cohens_d']:.4f} (baseline={result.get('baseline_f201_cohens_d', 0.0557):.4f}, beats_baseline={result.get('beats_baseline', False)})")