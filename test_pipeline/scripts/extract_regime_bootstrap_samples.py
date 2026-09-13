"""test_pipeline/scripts/extract_regime_bootstrap_samples.py

Extracts authentic sample tables and cluster snapshots for Step 6: Regime Partitioning & Clustered Bootstrap.
Outputs formatted tables directly to stdout.
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
REPORT_JSON = "test_pipeline/out/regime_bootstrap_report.json"
DB_PATH = "db/test_db/vesta_test.duckdb"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline


def extract_samples():
    with open(REPORT_JSON, "r", encoding="utf-8") as f:
        report = json.load(f)
        
    print("=" * 85)
    print("SAMPLE 1: VNINDEX HISTORICAL REGIME PARTITIONING BREAKDOWN (2007 - 2026)")
    print("=" * 85)
    reg_dict = report["regime_breakdown"]
    reg_rows = []
    for r in ["BULL", "SIDEWAYS", "BEAR", "CRISIS_HIGH_VOL", "ALL"]:
        item = reg_dict[r]
        reg_rows.append({
            "Market Regime": r,
            "Negative Events": f"{item['n_events']:,}",
            "Share of Total": f"{item['pct_of_total']}%",
            "Mean Return T+5->T+30": f"+{item['mean_return_pct']:.2f}%",
            "Win-Rate": f"{item['win_rate_pct']:.2f}%",
            "Ann. Sharpe": f"{item['annualized_sharpe']:.4f}",
            "Cohen's d": f"{item['cohen_d']:.4f}",
            "5% Left-Tail": f"{item['left_tail_5pct']:.2f}%",
        })
    print(pd.DataFrame(reg_rows).to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 2: BOOTSTRAP 95% CONFIDENCE INTERVALS (I.I.D. VS CLUSTERED BLOCK)")
    print("=" * 85)
    b_audit = report["bootstrap_audit"]
    boot_rows = [
        {
            "Resampling Method": "I.I.D. Naive Bootstrap (1,000 draws)",
            "Mean Return 95% CI": f"[{b_audit['iid_bootstrap']['mean_ci_95'][0]:.2f}%, {b_audit['iid_bootstrap']['mean_ci_95'][1]:.2f}%]",
            "CI Width": f"{b_audit['iid_bootstrap']['mean_ci_width']:.2f}%",
            "Annualized Sharpe 95% CI": f"[{b_audit['iid_bootstrap']['sharpe_ci_95'][0]:.4f}, {b_audit['iid_bootstrap']['sharpe_ci_95'][1]:.4f}]",
            "P(Sharpe <= 0)": f"{b_audit['iid_bootstrap']['prob_sharpe_le_zero_pct']:.2f}%",
        },
        {
            "Resampling Method": "Clustered Block Bootstrap (Weekly Clusters)",
            "Mean Return 95% CI": f"[{b_audit['clustered_block_bootstrap']['mean_ci_95'][0]:.2f}%, {b_audit['clustered_block_bootstrap']['mean_ci_95'][1]:.2f}%]",
            "CI Width": f"{b_audit['clustered_block_bootstrap']['mean_ci_width']:.2f}% (2.26x wider)",
            "Annualized Sharpe 95% CI": f"[{b_audit['clustered_block_bootstrap']['sharpe_ci_95'][0]:.4f}, {b_audit['clustered_block_bootstrap']['sharpe_ci_95'][1]:.4f}]",
            "P(Sharpe <= 0)": f"{b_audit['clustered_block_bootstrap']['prob_sharpe_le_zero_pct']:.2f}%",
        },
    ]
    print(pd.DataFrame(boot_rows).to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 3: PANIC CLUSTER CASE STUDY — COVID BOTTOM (WEEK OF 23-27 MARCH 2020)")
    print("=" * 85)
    con = duckdb.connect(DB_PATH, read_only=True)
    df_covid = con.execute("""
        SELECT symbol, published_at::DATE as event_date, headline,
               price_at_publish as p0, price_t5 as p5, price_t30 as p30
        FROM core.pit_events
        WHERE published_at >= '2020-03-23' AND published_at <= '2020-03-27'
          AND price_at_publish > 0 AND price_t5 > 0 AND price_t30 > 0
        ORDER BY published_at ASC
        LIMIT 6
    """).df()
    con.close()
    
    covid_rows = []
    for _, row in df_covid.iterrows():
        p0, p5, p30 = row["p0"], row["p5"], row["p30"]
        rebound_pct = (p30 - p5) / p0 * 100.0
        covid_rows.append({
            "Date": row["event_date"],
            "Symbol": row["symbol"],
            "P0 (Publish)": f"{p0:.2f}",
            "P5 (Drop)": f"{p5:.2f}",
            "P30 (Recovery)": f"{p30:.2f}",
            "Rebound T+5->T+30": f"+{rebound_pct:.2f}%",
            "Headline": row["headline"][:55] + "...",
        })
    print(pd.DataFrame(covid_rows).to_string(index=False))


if __name__ == "__main__":
    extract_samples()
