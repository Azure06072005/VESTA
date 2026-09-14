"""Generates publication-quality 4-panel diagnostic visualization for Module 3: Fractional Differentiation (FracDiff).

Panel 1: Power-Law Weight Decay Curves omega_k vs Lag k across d in {0.1, 0.3, 0.5, 0.7, 1.0}.
Panel 2: Stationarity vs. Memory Dilemma Curve (ADF p-val & Correlation vs d for HPG).
Panel 3: Multi-Horizon Trajectory Comparison (Raw Price d=0 vs Daily Diff d=1.0 vs FracDiff d=0.30).
Panel 4: Cross-Sectional Optimal d* & Memory Retention (R^2) across VN30 Flagships.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from test_pipeline.f1xx_enrichment.test_fractional_differentiation import (
    frac_diff_ffd,
    get_weights_ffd,
)


def generate_fracdiff_figure():
    sns.set_theme(style="darkgrid")
    fig, axes = plt.subplots(2, 2, figsize=(18, 14), dpi=300)

    # -------------------------------------------------------------
    # Panel 1: Power-Law Weight Decay Curves omega_k vs Lag k
    # -------------------------------------------------------------
    ax1 = axes[0, 0]
    d_list = [0.1, 0.3, 0.5, 0.7, 1.0]
    palette = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]

    for d_val, color in zip(d_list, palette):
        w = get_weights_ffd(d_val, thres=1e-5, max_k=250)
        lags = np.arange(len(w))
        label_str = f"d = {d_val:.1f}" + (" (Integer Return)" if d_val == 1.0 else "")
        ax1.plot(lags[:60], np.abs(w[:60]), label=label_str, color=color, linewidth=2.2 if d_val in (0.3, 1.0) else 1.5)

    ax1.axhline(1e-4, color="black", linestyle=":", linewidth=1.2, label="Truncation Threshold tau = 1e-4")
    ax1.set_yscale("log")
    ax1.set_title("Panel 1: Memory Weight Decay Profile |omega_k| vs Lag k", fontsize=13, fontweight="bold", pad=12)
    ax1.set_xlabel("Memory Lag k (Trading Days)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Absolute Weight |omega_k| (Log Scale)", fontsize=11, fontweight="bold")
    ax1.set_ylim(1e-5, 1.5)
    ax1.legend(loc="upper right", frameon=True, fontsize=9.5)

    # -------------------------------------------------------------
    # Panel 2: Stationarity vs. Memory Dilemma Curve (HPG Case Study)
    # -------------------------------------------------------------
    ax2 = axes[0, 1]
    with open("test_pipeline/out/fracdiff_benchmark_report.json", "r", encoding="utf-8") as f:
        report = json.load(f)

    hpg_grid = report["details"]["HPG"]["grid"]
    df_grid = pd.DataFrame(hpg_grid)

    ax2_twin = ax2.twinx()

    line1 = ax2.plot(df_grid["d"], df_grid["p_val"], color="#ef4444", marker="o", linewidth=2.4, label="ADF Test p-value (Stationarity)")
    ax2.axhline(0.01, color="#b91c1c", linestyle="--", linewidth=1.5, label="Stationarity Threshold (p = 0.01)")

    line2 = ax2_twin.plot(df_grid["d"], df_grid["corr"], color="#10b981", marker="s", linewidth=2.4, label="Correlation with Raw Price (Memory)")

    # Highlight optimal d* = 0.30
    hpg_opt = [r for r in hpg_grid if r["d"] == 0.30][0]
    ax2.scatter([0.30], [hpg_opt["p_val"]], color="#4f46e5", s=140, zorder=5)
    ax2.annotate(
        f"Optimal d* = 0.30\nADF p = {hpg_opt['p_val']:.4f}\nCorr r = {hpg_opt['corr']:.4f}",
        xy=(0.30, hpg_opt["p_val"]),
        xytext=(0.42, 0.45),
        arrowprops=dict(facecolor="#4f46e5", shrink=0.08, width=2, headwidth=7),
        fontweight="bold", fontsize=9.5, color="#312e81",
        bbox=dict(boxstyle="round,pad=0.3", fc="#e0e7ff", ec="#6366f1", lw=1.5),
    )

    ax2.set_title("Panel 2: Stationarity vs. Memory Dilemma (HPG 2007–2026)", fontsize=13, fontweight="bold", pad=12)
    ax2.set_xlabel("Differentiation Order d", fontsize=11, fontweight="bold")
    ax2.set_ylabel("ADF p-value (Lower = More Stationary)", fontsize=11, fontweight="bold", color="#b91c1c")
    ax2_twin.set_ylabel("Pearson Correlation r (Higher = More Memory)", fontsize=11, fontweight="bold", color="#059669")
    ax2.set_ylim(-0.05, 1.05)
    ax2_twin.set_ylim(-0.05, 1.05)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax2.legend(lines, labels, loc="center right", frameon=True, fontsize=9)

    # -------------------------------------------------------------
    # Panel 3: Time-Series Trajectory Comparison (HPG 2020–2026)
    # -------------------------------------------------------------
    ax3 = axes[1, 0]
    con = duckdb.connect("db/test_db/vesta_test.duckdb", read_only=True)
    df_hpg = con.execute("""
        SELECT date, close 
        FROM core.market_ohlcv_daily 
        WHERE symbol = 'HPG' AND date >= '2020-01-01'
        ORDER BY date
    """).df()
    con.close()

    s_log = pd.Series(np.log(df_hpg["close"].values), index=pd.to_datetime(df_hpg["date"]))
    s_fd = frac_diff_ffd(s_log, d=0.30, thres=1e-4)
    s_ret = s_log.diff().dropna()

    # Normalize to z-score for visual comparison
    z_raw = (s_log.loc[s_fd.index] - s_log.loc[s_fd.index].mean()) / s_log.loc[s_fd.index].std()
    z_fd = (s_fd - s_fd.mean()) / s_fd.std()
    z_ret = (s_ret.loc[s_fd.index] - s_ret.loc[s_fd.index].mean()) / s_ret.loc[s_fd.index].std()

    dates = s_fd.index
    ax3.plot(dates, z_raw, label="Raw Log Price (d = 0.0, Non-stationary)", color="#3b82f6", alpha=0.5, linewidth=1.8)
    ax3.plot(dates, z_fd, label="FracDiff (d* = 0.30, Stationary + Preserves Cycle)", color="#10b981", linewidth=2.0)
    ax3.plot(dates, z_ret, label="Daily Return (d = 1.0, White Noise, Zero Memory)", color="#ef4444", alpha=0.35, linewidth=0.8)

    ax3.axhline(0, color="black", linestyle="--", linewidth=1.0)
    ax3.set_title("Panel 3: Normalized Trajectories Comparison (HPG 2020–2026)", fontsize=13, fontweight="bold", pad=12)
    ax3.set_xlabel("Time (Trading Year)", fontsize=11, fontweight="bold")
    ax3.set_ylabel("Standardized Z-Score", fontsize=11, fontweight="bold")
    ax3.legend(loc="upper left", frameon=True, fontsize=9)

    # -------------------------------------------------------------
    # Panel 4: Cross-Sectional Optimal d* & Memory Retention (R^2)
    # -------------------------------------------------------------
    ax4 = axes[1, 1]
    summary_data = report["summary"]
    symbols = [s["symbol"] for s in summary_data]
    d_stars = [s["optimal_d"] for s in summary_data]
    r2_vals = [s["memory_retention_r2"] * 100 for s in summary_data]

    x_pts = np.arange(len(symbols))
    width = 0.35

    bars_d = ax4.bar(x_pts - width/2, d_stars, width=width, color="#6366f1", alpha=0.85, label="Optimal d* (ADF p <= 0.01)")
    bars_r2 = ax4.bar(x_pts + width/2, [r/100 for r in r2_vals], width=width, color="#10b981", alpha=0.85, label="Memory Retention R^2 (%)")

    for bar, val in zip(bars_d, d_stars):
        ax4.annotate(f"d={val:.2f}", xy=(bar.get_x() + bar.get_width()/2, val),
                     xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8.5, fontweight="bold")

    for bar, val in zip(bars_r2, r2_vals):
        ax4.annotate(f"{val:.1f}%", xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                     xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8.5, fontweight="bold", color="#065f46")

    ax4.set_title("Panel 4: Cross-Sectional Optimal d* & Memory Retention R^2 across VN30 Flagships", fontsize=13, fontweight="bold", pad=12)
    ax4.set_xticks(x_pts)
    ax4.set_xticklabels(symbols, fontsize=10, fontweight="bold")
    ax4.set_ylabel("Metric Value (d* / R^2)", fontsize=11, fontweight="bold")
    ax4.set_ylim(0, 1.25)
    ax4.legend(loc="upper right", frameon=True, fontsize=9.5)

    plt.suptitle("VESTA Data Preprocessing — Module 3: Fractional Differentiation (FracDiff FFD)\n"
                 "Balancing Statistical Stationarity (ADF p < 0.01) with 90.6% Long-Term Memory Preservation",
                 fontsize=14, fontweight="bold", y=0.995)
    plt.tight_layout(rect=[0, 0.03, 1, 0.96])

    out_file = Path("test_pipeline/out/fracdiff_diagnostics.png")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close()

    # Copy to artifact directory
    artifact_dir = Path("C:/Users/ADMIN/.gemini/antigravity-ide/brain/2ebb0c09-579b-48e8-91b8-599a5f512f13")
    if artifact_dir.exists():
        dest = artifact_dir / "fracdiff_diagnostics.png"
        shutil.copy(out_file, dest)
        print(f"[+] Successfully copied diagnostic figure to artifact directory: {dest}")

    print(f"[+] FracDiff diagnostic figure generated: {out_file}")


if __name__ == "__main__":
    generate_fracdiff_figure()
