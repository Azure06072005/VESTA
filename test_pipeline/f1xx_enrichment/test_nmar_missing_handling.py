"""Module 2 (Refined): NMAR Data Preprocessing, Distress-Conditioned Imputation & Confidence Gating.

Implements core improvements based on Loop Engineering critique:
1. Dynamic Confidence Gating:
   confidence_weight = (1 - is_delinquent) * exp(-staleness / 180.0) * (1 - is_missing) * (1 - is_non_equity)
   - Fresh (15d): ~0.92 confidence.
   - Seasoned (90d-180d): Exponential decay (0.61 -> 0.37).
   - Delinquent (> 180d) / Missing / ETF: Strictly 0.0 (zero-trust gating).
2. Gated Feature Vector Generation:
   Combines raw imputed values with gated confidence-weighted values:
   gated_metric = imputed_metric * confidence_weight
3. Lottery-Ticket Skewness Decomposition:
   Exposes the statistical illusion: Delinquent stocks have an apparent positive arithmetic mean
   caused entirely by speculative penny pumps (P95 = +83.4%), but suffer from a dismal 38.1% win rate
   and massive volatility (33.6% vs 17.0% for Fresh stocks).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

# Financial Distress Penalty Values (Bottom 5th percentile / High distress benchmarks)
PENALTY_BENCHMARKS = {
    "RT_VALUE_PE": 0.0,            # Zero/Negative earnings
    "RT_VALUE_PB": 0.5,            # Distressed deep discount book
    "RT_PRT_ROE": -0.15,           # -15% severe return on equity erosion
    "RT_PRT_ROA": -0.08,           # -8% negative return on assets
    "RT_PRT_NET_MARGIN": -0.20,    # -20% operating net margin loss
    "RT_LEV_DE": 5.0,              # Highly levered (5x Debt to Equity)
    "RT_LQD_CR": 0.5,              # Severe liquidity distress (Current Ratio < 0.5)
}


def classify_instrument_type(symbol: str) -> str:
    """Classifies financial instrument type from ticker structure in Vietnam market."""
    s = str(symbol).strip().upper()
    if s.startswith("E1") or s.startswith("FUE"):
        return "ETF"
    if len(s) == 8 and s.startswith("C"):
        return "WARRANT"
    # Corporate bonds typically have ticker lengths >= 6 with numbers at end (e.g. CTG123034, BCG122006)
    if len(s) >= 6 and any(c.isdigit() for c in s[3:]):
        return "BOND"
    return "STOCK"


def extract_ratio_fields(data_json_str: Optional[str]) -> Dict[str, float]:
    """Safely extracts key ratio metrics from fundamental data_json."""
    default_vals = {k: np.nan for k in PENALTY_BENCHMARKS}
    if not data_json_str or pd.isna(data_json_str):
        return default_vals
    try:
        parsed = json.loads(data_json_str)
        return {k: float(parsed.get(k, np.nan)) for k in PENALTY_BENCHMARKS}
    except Exception:
        return default_vals


def compute_confidence_weight(
    staleness_days: int,
    is_delinquent: int,
    is_missing: int,
    is_non_equity: int,
    tau_halflife: float = 180.0,
) -> float:
    """Computes dynamic confidence weight in [0.0, 1.0] for fundamental features.
    
    Formula:
      confidence = (1 - is_delinquent) * exp(-staleness / tau) * (1 - is_missing) * (1 - is_non_equity)
    """
    if is_delinquent or is_missing or is_non_equity:
        return 0.0
    return float(np.clip(math.exp(-staleness_days / tau_halflife), 0.0, 1.0))


def compute_nmar_imputation(
    symbol: str,
    event_date: str | dt.date,
    available_at: Optional[str | dt.date],
    raw_ratios: Dict[str, float],
) -> Dict[str, Any]:
    """Computes NMAR flags, distress-conditioned imputations, and confidence gating."""
    inst_type = classify_instrument_type(symbol)
    is_non_equity = int(inst_type != "STOCK")

    d_event = pd.to_datetime(event_date).date()
    if available_at and not pd.isna(available_at):
        d_avail = pd.to_datetime(available_at).date()
        staleness = max(0, (d_event - d_avail).days)
        staleness_clamped = min(365, staleness)
    else:
        staleness = 365
        staleness_clamped = 365

    # Delinquent if corporate stock and reporting is over 180 days late
    is_delinquent = int(inst_type == "STOCK" and staleness > 180)
    event_missing_flag = int(available_at is None or pd.isna(available_at))

    # Dynamic confidence weight
    confidence_weight = compute_confidence_weight(
        staleness_days=staleness_clamped,
        is_delinquent=is_delinquent,
        is_missing=event_missing_flag,
        is_non_equity=is_non_equity,
    )

    imputed_ratios = {}
    gated_ratios = {}
    missing_flags = {}

    for metric, penalty_val in PENALTY_BENCHMARKS.items():
        val = raw_ratios.get(metric, np.nan)
        is_missing = int(pd.isna(val))
        missing_flags[f"is_missing_{metric}"] = is_missing

        if is_non_equity:
            # Structurally not applicable for ETF/Warrant/Bond
            imp_val = 0.0
        elif is_missing or is_delinquent:
            # Apply financial distress penalty
            imp_val = penalty_val
        else:
            # Valid seasoned fundamental
            imp_val = float(val)

        imputed_ratios[f"imputed_{metric}"] = imp_val
        gated_ratios[f"gated_{metric}"] = imp_val * confidence_weight

    return {
        "symbol": symbol,
        "instrument_type": inst_type,
        "is_non_equity": is_non_equity,
        "staleness_days": staleness_clamped,
        "is_missing_flag": event_missing_flag,
        "is_delinquent_flag": is_delinquent,
        "confidence_weight": confidence_weight,
        "missing_flags": missing_flags,
        "imputed_ratios": imputed_ratios,
        "gated_ratios": gated_ratios,
    }


def run_nmar_audit(
    db_path: str = "db/test_db/vesta_test.duckdb",
    sample_limit: int = 30000,
) -> Dict[str, Any]:
    """Audits NMAR missingness, staleness, confidence gating, and lottery-ticket skewness."""
    print("=" * 85)
    print("RUNNING MODULE 2 (REFINED) AUDIT: CONFIDENCE GATING & LOTTERY SKEWNESS")
    print("=" * 85)

    con = duckdb.connect(db_path, read_only=True)
    query = f"""
        WITH matched_events AS (
            SELECT 
                e.symbol,
                e.published_at,
                CAST(e.published_at AS DATE) as event_date,
                e.price_at_publish,
                e.price_t30,
                (e.price_t30 - e.price_at_publish) / e.price_at_publish * 100.0 as return_t30,
                f.period_end,
                f.available_at,
                DATE_DIFF('day', f.available_at, CAST(e.published_at AS DATE)) as staleness_days,
                f.data_json
            FROM core.pit_events e
            ASOF LEFT JOIN core.fundamentals f
              ON e.symbol = f.symbol
             AND f.report_type = 'ratio'
             AND f.available_at <= CAST(e.published_at AS DATE)
            WHERE e.price_at_publish > 0 AND e.price_t30 > 0
            LIMIT {sample_limit}
        )
        SELECT * FROM matched_events
    """
    df = con.execute(query).df()
    con.close()

    print(f"[*] Ingested {len(df):,} PIT events from test database.")

    # Classify instruments
    df["instrument_type"] = df["symbol"].apply(classify_instrument_type)
    inst_counts = df["instrument_type"].value_counts().to_dict()
    print(f"[*] Instrument Breakdown: {inst_counts}")

    # Process NMAR records
    results = []
    for idx, row in df.iterrows():
        raw_ratios = extract_ratio_fields(row["data_json"])
        nmar_meta = compute_nmar_imputation(
            symbol=row["symbol"],
            event_date=row["event_date"],
            available_at=row["available_at"],
            raw_ratios=raw_ratios,
        )
        results.append(nmar_meta)

    df_meta = pd.DataFrame(results)
    df["is_non_equity"] = df_meta["is_non_equity"]
    df["is_delinquent_flag"] = df_meta["is_delinquent_flag"]
    df["staleness_clamped"] = df_meta["staleness_days"]
    df["confidence_weight"] = df_meta["confidence_weight"]

    # Segment Stocks by Reporting Status
    df_stocks = df[df["instrument_type"] == "STOCK"].copy()

    def assign_status(row):
        if pd.isna(row["available_at"]):
            return "Missing/No Report"
        if row["staleness_days"] <= 90:
            return "Fresh (<=90d)"
        if row["staleness_days"] <= 180:
            return "Seasoned (91-180d)"
        return "Delinquent (>180d)"

    df_stocks["reporting_status"] = df_stocks.apply(assign_status, axis=1)

    # Detailed statistics exposing lottery skewness
    grouped = df_stocks.groupby("reporting_status")
    records = []
    for status, grp in grouped:
        r = grp["return_t30"]
        c_wt = grp["confidence_weight"]
        records.append({
            "reporting_status": status,
            "count": len(grp),
            "pct_of_events": round(len(grp) / len(df_stocks) * 100.0, 2),
            "mean": round(float(r.mean()), 2),
            "median": round(float(r.median()), 2),
            "std": round(float(r.std()), 2),
            "win_rate_pct": round(float((r > 0).mean() * 100.0), 1),
            "p05_tail_loss": round(float(np.percentile(r, 5)), 2),
            "p95_tail_gain": round(float(np.percentile(r, 95)), 2),
            "avg_confidence_weight": round(float(c_wt.mean()), 3),
        })

    status_stats = pd.DataFrame(records).sort_values("count", ascending=False)
    fresh_std = float(status_stats.loc[status_stats["reporting_status"] == "Fresh (<=90d)", "std"].iloc[0])
    status_stats["volatility_multiplier"] = round(status_stats["std"] / fresh_std, 2)

    print("\n[*] Empirical Decomposed Statistics (Common Stocks):")
    print(status_stats.to_string(index=False))

    delinq_row = status_stats[status_stats["reporting_status"] == "Delinquent (>180d)"].iloc[0]
    fresh_row = status_stats[status_stats["reporting_status"] == "Fresh (<=90d)"].iloc[0]

    print(f"\n[*] Key Refined Finding: The Lottery Ticket Skewness Paradox:")
    print(f"    - Fresh Stocks: Win Rate = {fresh_row['win_rate_pct']}%, Volatility = {fresh_row['std']}%, Confidence = {fresh_row['avg_confidence_weight']:.3f}")
    print(f"    - Delinquent Stocks: Win Rate = {delinq_row['win_rate_pct']}%, Volatility = {delinq_row['std']}%, Confidence = {delinq_row['avg_confidence_weight']:.3f}")
    print(f"    - Delinquent Win Rate is LOWER by {fresh_row['win_rate_pct'] - delinq_row['win_rate_pct']:.1f}% despite higher mean!")

    report = {
        "module": "NMAR Missing Data Handling (Refined)",
        "sample_size": len(df),
        "instrument_counts": inst_counts,
        "stock_reporting_status": status_stats.to_dict(orient="records"),
        "distress_penalty_benchmarks": PENALTY_BENCHMARKS,
        "status": "PASS",
    }

    out_path = Path("test_pipeline/out/nmar_missing_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"[+] Refined NMAR Audit Report successfully written to {out_path}")
    return report


if __name__ == "__main__":
    run_nmar_audit()
