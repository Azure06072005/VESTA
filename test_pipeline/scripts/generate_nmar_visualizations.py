"""Generates publication-quality 4-panel diagnostic visualization for Module 2 (Refined): NMAR Missing Data Handling.

Updated with Confidence Gating & Lottery Skewness Decomposition:
Panel 1: Reporting Status Breakdown Across Common Stocks.
Panel 2: The Lottery-Ticket Paradox: Win Rate (%) vs Volatility (%) across Reporting Tiers.
Panel 3: Dynamic Confidence Gating Weight Curve (exp(-t/180) & Hard Zero Cutoff).
Panel 4: Dual-Channel Neural Vector (Imputed vs Gated Ratios w * X).
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from test_pipeline.f1xx_enrichment.test_nmar_missing_handling import (
    PENALTY_BENCHMARKS,
    classify_instrument_type,
    compute_confidence_weight,
)


def generate_nmar_figure():
    sns.set_theme(style="darkgrid")
    fig, axes = plt.subplots(2, 2, figsize=(18, 14), dpi=300)

    # 1. Load data from report
    report_file = Path("test_pipeline/out/nmar_missing_report.json")
    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    status_data = report["stock_reporting_status"]
    categories = [s["reporting_status"] for s in status_data]
    counts = [s["count"] for s in status_data]
    colors = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444"]

    # Panel 1: Reporting Status Breakdown
    ax1 = axes[0, 0]
    bars1 = ax1.bar(categories, counts, color=colors, alpha=0.9, width=0.55)
    for bar in bars1:
        height = bar.get_height()
        ax1.annotate(f"{height:,}\n({height/sum(counts)*100:.1f}%)",
                     xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 5), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9.5, fontweight="bold")

    ax1.set_title("Panel 1: Reporting Status Distribution (Sample Size: 12,613 Stocks)", fontsize=13, fontweight="bold", pad=12)
    ax1.set_ylabel("Number of Observations", fontsize=11, fontweight="bold")
    ax1.set_ylim(0, max(counts) * 1.2)

    # Panel 2: The Lottery-Ticket Paradox: Win Rate (%) vs Volatility (%)
    ax2 = axes[0, 1]
    win_rates = [s["win_rate_pct"] for s in status_data]
    stds = [s["std"] for s in status_data]

    x_indices = np.arange(len(categories))
    width = 0.35

    bars_win = ax2.bar(x_indices - width/2, win_rates, width=width, color="#059669", alpha=0.85, label="Win Rate (% Return > 0)")
    bars_vol = ax2.bar(x_indices + width/2, stds, width=width, color="#dc2626", alpha=0.85, label="Volatility (T+30 Std Dev %)")

    for bar, wr in zip(bars_win, win_rates):
        h = bar.get_height()
        ax2.annotate(f"{wr:.1f}%", xy=(bar.get_x() + bar.get_width()/2, h), xytext=(0, 4), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9, fontweight="bold", color="#065f46")

    for bar, vol in zip(bars_vol, stds):
        h = bar.get_height()
        ax2.annotate(f"{vol:.1f}%", xy=(bar.get_x() + bar.get_width()/2, h), xytext=(0, 4), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9, fontweight="bold", color="#991b1b")

    delinq_idx = [i for i, c in enumerate(categories) if "Delinquent" in c][0]
    ax2.annotate(
        "Lottery Paradox:\nLowest Win Rate (39.5%)\nHigh Volatility (22.5%)",
        xy=(delinq_idx, win_rates[delinq_idx]),
        xytext=(delinq_idx - 0.7, 48),
        arrowprops=dict(facecolor="#b91c1c", shrink=0.08, width=2, headwidth=7),
        fontweight="bold", fontsize=9, color="#991b1b",
        bbox=dict(boxstyle="round,pad=0.3", fc="#fee2e2", ec="#f87171", lw=1.5),
    )

    ax2.set_title("Panel 2: The Lottery Paradox — Win Rate (%) vs Volatility (%)", fontsize=13, fontweight="bold", pad=12)
    ax2.set_xticks(x_indices)
    ax2.set_xticklabels(categories, fontsize=9.5, fontweight="bold")
    ax2.set_ylabel("Percentage (%)", fontsize=11, fontweight="bold")
    ax2.set_ylim(0, 65)
    ax2.legend(loc="upper right", frameon=True, fontsize=9.5)

    # Panel 3: Dynamic Confidence Gating Weight Curve
    ax3 = axes[1, 0]
    days = np.linspace(0, 365, 500)
    weights = []
    for d in days:
        if d <= 180:
            weights.append(compute_confidence_weight(int(d), 0, 0, 0, tau_halflife=180.0))
        else:
            weights.append(0.0) # Delinquent hard zero

    ax3.plot(days, weights, color="#4f46e5", linewidth=2.8, label="Confidence Weight w(t)")
    ax3.fill_between(days, weights, color="#818cf8", alpha=0.25)

    ax3.axvline(90, color="#10b981", linestyle="--", linewidth=1.8, label="90d Seasoned Threshold (w = 0.61)")
    ax3.axvline(180, color="#ef4444", linestyle="--", linewidth=2.2, label="180d Delinquency Cutoff (w -> 0.0)")

    ax3.annotate("Fresh Filing Zone\n(High Model Confidence)", xy=(20, 0.85), xytext=(20, 0.85),
                 fontweight="bold", color="#059669", fontsize=9.5)
    ax3.annotate("DELINQUENCY ZONE (w = 0.0)\nZero-Trust Neural Attention Gate", xy=(195, 0.4), xytext=(205, 0.4),
                 fontweight="bold", color="#dc2626", fontsize=9.5,
                 bbox=dict(boxstyle="round,pad=0.3", fc="#fee2e2", ec="#ef4444", lw=1.2))

    ax3.set_title("Panel 3: Dynamic Confidence Gating Weight w(t) = exp(-t / 180)", fontsize=13, fontweight="bold", pad=12)
    ax3.set_xlabel("Staleness (Calendar Days Since Statutory Publication)", fontsize=11, fontweight="bold")
    ax3.set_ylabel("Confidence Weight (0.0 to 1.0)", fontsize=11, fontweight="bold")
    ax3.set_ylim(-0.05, 1.1)
    ax3.legend(loc="upper right", frameon=True, fontsize=9.5)

    # Panel 4: Dual-Channel Neural Representation: Raw Imputed vs Gated Values
    ax4 = axes[1, 1]
    case_names = [
        "Fresh Firm\n(Stale 20d, w=0.89)",
        "Seasoned Firm\n(Stale 120d, w=0.51)",
        "Delinquent Firm\n(Stale 220d, w=0.0)",
        "Missing BCTC\n(Audit Risk, w=0.0)",
    ]
    raw_imputed_roe = [18.0, 18.0, -15.0, -15.0]
    conf_w = [0.895, 0.513, 0.0, 0.0]
    gated_roe = [r * w for r, w in zip(raw_imputed_roe, conf_w)]

    x_pts = np.arange(len(case_names))
    ax4.bar(x_pts - width/2, raw_imputed_roe, width=width, color="#3b82f6", alpha=0.85, label="Raw Imputed ROE (%) [Preserves Distress Penalty]")
    ax4.bar(x_pts + width/2, gated_roe, width=width, color="#10b981", alpha=0.9, label="Gated ROE w*X (%) [Neural Attention Channel]")

    for bar, val in zip(ax4.patches[:4], raw_imputed_roe):
        ax4.annotate(f"{val:+.1f}%", xy=(bar.get_x() + bar.get_width()/2, val),
                     xytext=(0, 4 if val >= 0 else -14), textcoords="offset points",
                     ha="center", fontsize=9, fontweight="bold")

    for bar, val in zip(ax4.patches[4:], gated_roe):
        ax4.annotate(f"{val:+.1f}%", xy=(bar.get_x() + bar.get_width()/2, val),
                     xytext=(0, 4 if val >= 0 else -14), textcoords="offset points",
                     ha="center", fontsize=9, fontweight="bold")

    ax4.axhline(0, color="black", linewidth=1.2)
    ax4.set_title("Panel 4: Dual-Channel Neural Vector — Raw Imputed vs Gated Feature", fontsize=13, fontweight="bold", pad=12)
    ax4.set_xticks(x_pts)
    ax4.set_xticklabels(case_names, fontsize=8.5, fontweight="bold")
    ax4.set_ylabel("ROE Value (%)", fontsize=11, fontweight="bold")
    ax4.set_ylim(-22, 26)
    ax4.legend(loc="lower left", frameon=True, fontsize=9)

    plt.suptitle("VESTA Data Preprocessing — Module 2 (Refined): Confidence Gating & Lottery Skewness\n"
                 "Dual-Channel Representation Resolves Accounting Invariance & Delinquency Volatility",
                 fontsize=14, fontweight="bold", y=0.995)
    plt.tight_layout(rect=[0, 0.03, 1, 0.96])

    out_file = Path("test_pipeline/out/nmar_missing_data_diagnostics.png")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()

    # Copy to artifact directory
    artifact_dir = Path("C:/Users/ADMIN/.gemini/antigravity-ide/brain/2ebb0c09-579b-48e8-91b8-599a5f512f13")
    if artifact_dir.exists():
        dest = artifact_dir / "nmar_missing_data_diagnostics.png"
        shutil.copy(out_file, dest)
        print(f"[+] Successfully copied diagnostic figure to artifact directory: {dest}")

    print(f"[+] Diagnostic figure generated: {out_file}")


if __name__ == "__main__":
    generate_nmar_figure()
