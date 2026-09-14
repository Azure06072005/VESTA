"""Extracts raw representative data samples for Module 2 (Refined): NMAR Missing Data Handling.

Updated with Confidence Gating & Dual-Channel Neural Vector.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_pipeline.f1xx_enrichment.test_nmar_missing_handling import (
    PENALTY_BENCHMARKS,
    classify_instrument_type,
    compute_nmar_imputation,
    extract_ratio_fields,
)


def extract_samples():
    print("=" * 105)
    print("TABLE 1: EMPIRICAL RISK & SKEWNESS DECOMPOSITION (12,613 COMMON STOCKS IN DUCKDB)")
    print("=" * 105)

    with open("test_pipeline/out/nmar_missing_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    df_stats = pd.DataFrame(data["stock_reporting_status"])
    cols_order = [
        "reporting_status", "count", "pct_of_events", "win_rate_pct",
        "mean", "median", "std", "p05_tail_loss", "p95_tail_gain", "avg_confidence_weight"
    ]
    print(df_stats[cols_order].to_string(index=False))

    print("\n" + "=" * 105)
    print("TABLE 2: THE LOTTERY SKEWNESS PARADOX: FRESH VS DELINQUENT STOCKS")
    print("=" * 105)

    fresh = df_stats[df_stats["reporting_status"] == "Fresh (<=90d)"].iloc[0]
    delinq = df_stats[df_stats["reporting_status"] == "Delinquent (>180d)"].iloc[0]

    paradox_rows = [
        {"Risk / Performance Metric": "Win Rate (% Positive Trades)", "Fresh (<=90d)": f"{fresh['win_rate_pct']}%", "Delinquent (>180d)": f"{delinq['win_rate_pct']}%", "Implication": "Delinquent has 5.7% lower win rate (60.5% losing trades)"},
        {"Risk / Performance Metric": "Return Volatility (Std Dev)", "Fresh (<=90d)": f"{fresh['std']}%", "Delinquent (>180d)": f"{delinq['std']}%", "Implication": "Delinquent volatility is +36.8% higher"},
        {"Risk / Performance Metric": "5th Percentile Tail Loss (P05)", "Fresh (<=90d)": f"{fresh['p05_tail_loss']}%", "Delinquent (>180d)": f"{delinq['p05_tail_loss']}%", "Implication": "Severe downside tail risk in late filers"},
        {"Risk / Performance Metric": "95th Percentile Tail Gain (P95)", "Fresh (<=90d)": f"{fresh['p95_tail_gain']}%", "Delinquent (>180d)": f"{delinq['p95_tail_gain']}%", "Implication": "Penny squeeze creates lottery skewness trap"},
        {"Risk / Performance Metric": "Confidence Weight Gate w(t)", "Fresh (<=90d)": f"{fresh['avg_confidence_weight']:.3f}", "Delinquent (>180d)": f"{delinq['avg_confidence_weight']:.3f}", "Implication": "Zero-trust gate strictly zeros out untrusted fundamentals"},
    ]
    df_paradox = pd.DataFrame(paradox_rows)
    print(df_paradox.to_string(index=False))

    print("\n" + "=" * 105)
    print("TABLE 3: DUCKDB REAL EVENTS: DUAL-CHANNEL NEURAL REPRESENTATION (IMPUTED & GATED)")
    print("=" * 105)

    con = duckdb.connect("db/test_db/vesta_test.duckdb", read_only=True)
    df_raw = con.execute("""
        WITH matched AS (
            SELECT 
                e.symbol,
                e.published_at,
                CAST(e.published_at AS DATE) as event_date,
                e.price_at_publish,
                f.period_end,
                f.available_at,
                f.data_json
            FROM core.pit_events e
            ASOF LEFT JOIN core.fundamentals f
              ON e.symbol = f.symbol
             AND f.report_type = 'ratio'
             AND f.available_at <= CAST(e.published_at AS DATE)
            WHERE e.published_at IS NOT NULL
            ORDER BY e.published_at DESC
            LIMIT 15
        )
        SELECT * FROM matched
    """).df()
    con.close()

    rows = []
    for _, r in df_raw.iterrows():
        raw_ratios = extract_ratio_fields(r["data_json"])
        meta = compute_nmar_imputation(r["symbol"], r["event_date"], r["available_at"], raw_ratios)

        raw_roe_str = f"{raw_ratios.get('RT_PRT_ROE', np.nan)*100:.1f}%" if pd.notna(raw_ratios.get('RT_PRT_ROE')) else "NULL"
        imputed_roe_str = f"{meta['imputed_ratios']['imputed_RT_PRT_ROE']*100:.1f}%"
        gated_roe_str = f"{meta['gated_ratios']['gated_RT_PRT_ROE']*100:.1f}%"

        rows.append({
            "Symbol": r["symbol"],
            "Event Date": str(r["event_date"]),
            "Type": meta["instrument_type"],
            "Staleness": f"{meta['staleness_days']}d",
            "Delinq": meta["is_delinquent_flag"],
            "Confidence w": f"{meta['confidence_weight']:.3f}",
            "Raw ROE": raw_roe_str,
            "Imputed ROE": imputed_roe_str,
            "Gated ROE (w*X)": gated_roe_str,
        })

    df_sample = pd.DataFrame(rows)
    print(df_sample.to_string(index=False))


if __name__ == "__main__":
    extract_samples()
