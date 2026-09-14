"""test_pipeline/scripts/generate_sector_fracdiff_visualizations.py

Generates publication-quality 4-panel diagnostic dashboard for Dynamic Sector-Specific FracDiff:
1. Optimal d* by Sector (Highlighting Banking & Financials requiring d* >= 0.25).
2. ADF p-value vs d curves for representative sectors (Crossing the p = 0.01 gate).
3. Memory Retention (Correlation rho) Pareto curves.
4. Historical Signal Trajectory: Raw vs FracDiff(d*) vs Integer Diff (d=1).

Saves to:
- C:/Users/ADMIN/.gemini/antigravity-ide/brain/2ebb0c09-579b-48e8-91b8-599a5f512f13/sector_specific_fracdiff_diagnostics.png
- test_pipeline/out/sector_specific_fracdiff_diagnostics.png
"""
import json
import os
import shutil
import sys
import duckdb
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_fractional_differentiation import frac_diff_ffd
from test_pipeline.f1xx_enrichment.test_sector_specific_fracdiff import (
    extract_sector_price_series,
    DB_PATH,
    OUT_REPORT,
)

ARTIFACT_DIR = "C:/Users/ADMIN/.gemini/antigravity-ide/brain/2ebb0c09-579b-48e8-91b8-599a5f512f13"
OUT_IMG_TEST = "test_pipeline/out/sector_specific_fracdiff_diagnostics.png"
OUT_IMG_ARTIFACT = os.path.join(ARTIFACT_DIR, "sector_specific_fracdiff_diagnostics.png")


def generate_dashboard():
    with open(OUT_REPORT, "r", encoding="utf-8") as f:
        report = json.load(f)
        
    con = duckdb.connect(DB_PATH, read_only=True)
    sector_series = extract_sector_price_series(con)
    con.close()
    
    # Setup aesthetic dark/modern style
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), dpi=300)
    fig.patch.set_facecolor("#f8fafc")

    # -------------------------------------------------------------------------
    # Panel 1: Bar Chart of Optimal d* by Sector
    # -------------------------------------------------------------------------
    ax1 = axes[0, 0]
    ax1.set_facecolor("#ffffff")
    
    df_res = pd.DataFrame(report["results"]).sort_values("optimal_d", ascending=True)
    colors = []
    for _, r in df_res.iterrows():
        if r["optimal_d"] >= 0.25:
            colors.append("#ef4444")  # Red for high-persistence (Banking/Finance)
        elif r["optimal_d"] == 0.20:
            colors.append("#3b82f6")  # Blue for benchmark
        elif r["optimal_d"] == 0.15:
            colors.append("#10b981")  # Green for moderate
        else:
            colors.append("#8b5cf6")  # Purple for defensive
            
    bars = ax1.barh(df_res["sector"], df_res["optimal_d"], color=colors, edgecolor="#334155", alpha=0.85, height=0.65)
    ax1.axvline(0.20, color="#f59e0b", linestyle="--", linewidth=2.0, label="Uniform Global d=0.20 (VNINDEX Baseline)")
    
    for bar, d_val in zip(bars, df_res["optimal_d"]):
        ax1.text(d_val + 0.005, bar.get_y() + bar.get_height()/2, f"d*={d_val:.2f}", 
                 va="center", ha="left", fontsize=9.5, fontweight="bold", color="#1e293b")
        
    ax1.set_xlim(0, 0.32)
    ax1.set_title("Panel A: Optimal Fractional Order d* by Sector (ADF p <= 0.01)", fontsize=12, fontweight="bold", pad=10)
    ax1.set_xlabel("Optimal Fractional Order (d*)", fontsize=10, fontweight="bold")
    ax1.legend(loc="lower right", frameon=True, framealpha=0.9)
    ax1.grid(True, linestyle=":", alpha=0.6)

    # -------------------------------------------------------------------------
    # Panel 2: ADF p-value vs d curves
    # -------------------------------------------------------------------------
    ax2 = axes[0, 1]
    ax2.set_facecolor("#ffffff")
    
    rep_sectors = ["Ngân hàng", "Công nghiệp", "Dầu khí", "Tiện ích Cộng đồng"]
    rep_colors = {"Ngân hàng": "#ef4444", "Công nghiệp": "#3b82f6", "Dầu khí": "#10b981", "Tiện ích Cộng đồng": "#8b5cf6"}
    
    for sec_data in report["results"]:
        sec_name = sec_data["sector"]
        if sec_name in rep_sectors:
            gd = pd.DataFrame(sec_data["grid_details"])
            ax2.plot(gd["d"], gd["p_val"], marker="o", markersize=4, linewidth=2, 
                     color=rep_colors[sec_name], label=f"{sec_name} (d*={sec_data['optimal_d']:.2f})")
            
    ax2.axhline(0.01, color="#dc2626", linestyle="--", linewidth=1.8, label="Stationarity Threshold (p = 0.01)")
    ax2.axvline(0.20, color="#f59e0b", linestyle=":", linewidth=1.5, label="Global d=0.20 (Fails Banking)")
    ax2.set_yscale("log")
    ax2.set_ylim(1e-12, 1.0)
    ax2.set_title("Panel B: ADF p-value vs d (Log-Scale) — Sector Sensitivity", fontsize=12, fontweight="bold", pad=10)
    ax2.set_xlabel("Fractional Order (d)", fontsize=10, fontweight="bold")
    ax2.set_ylabel("ADF Test p-value (Log scale)", fontsize=10, fontweight="bold")
    ax2.legend(loc="upper right", frameon=True, framealpha=0.9, fontsize=9)
    ax2.grid(True, linestyle=":", alpha=0.6)

    # -------------------------------------------------------------------------
    # Panel 3: Memory Retention (Correlation rho) vs d
    # -------------------------------------------------------------------------
    ax3 = axes[1, 0]
    ax3.set_facecolor("#ffffff")
    
    for sec_data in report["results"]:
        sec_name = sec_data["sector"]
        if sec_name in rep_sectors:
            gd = pd.DataFrame(sec_data["grid_details"])
            ax3.plot(gd["d"], gd["corr"], marker="s", markersize=4, linewidth=2, 
                     color=rep_colors[sec_name], label=f"{sec_name}")
            # Mark optimal d* point
            opt_d = sec_data["optimal_d"]
            opt_corr = sec_data["optimal_corr"]
            ax3.scatter([opt_d], [opt_corr], s=120, color=rep_colors[sec_name], edgecolors="#0f172a", zorder=5)
            
    ax3.axhline(0.0, color="#64748b", linestyle="-", linewidth=1)
    ax3.axvline(1.0, color="#dc2626", linestyle="--", linewidth=1.5, label="Integer Diff d=1 (Destroys 99% Memory)")
    ax3.set_ylim(-0.05, 1.05)
    ax3.set_title("Panel C: Memory Preservation rho(X, X^(d)) vs d (Pareto Frontier)", fontsize=12, fontweight="bold", pad=10)
    ax3.set_xlabel("Fractional Order (d)", fontsize=10, fontweight="bold")
    ax3.set_ylabel("Pearson Correlation with Raw Price (rho)", fontsize=10, fontweight="bold")
    ax3.legend(loc="upper right", frameon=True, framealpha=0.9, fontsize=9)
    ax3.grid(True, linestyle=":", alpha=0.6)

    # -------------------------------------------------------------------------
    # Panel 4: Banking Sector Case Study (2020-2024 Trajectory)
    # -------------------------------------------------------------------------
    ax4 = axes[1, 1]
    ax4.set_facecolor("#ffffff")
    
    s_bank = sector_series["Ngân hàng"]
    s_bank_sub = s_bank.loc["2020-01-01":"2023-12-31"]
    
    # Calculate FracDiff d=0.25 (Optimal) and d=1.0 (Integer return)
    fd_bank_opt = frac_diff_ffd(s_bank, 0.25).loc["2020-01-01":"2023-12-31"]
    fd_bank_d1 = frac_diff_ffd(s_bank, 1.0).loc["2020-01-01":"2023-12-31"]
    
    # Normalize for visual comparison
    raw_norm = (s_bank_sub - s_bank_sub.mean()) / s_bank_sub.std()
    opt_norm = (fd_bank_opt - fd_bank_opt.mean()) / fd_bank_opt.std()
    d1_norm = (fd_bank_d1 - fd_bank_d1.mean()) / fd_bank_d1.std()
    
    ax4.plot(s_bank_sub.index, raw_norm, color="#0f172a", linewidth=1.8, label="Raw Log-Price (Non-stationary)", alpha=0.8)
    ax4.plot(opt_norm.index, opt_norm, color="#ef4444", linewidth=1.5, label="Sector FracDiff d*=0.25 (Stationary + Memory)", alpha=0.9)
    ax4.plot(d1_norm.index, d1_norm, color="#94a3b8", linewidth=0.8, label="Integer Return d=1 (White Noise)", alpha=0.6)
    
    ax4.set_title("Panel D: Banking Sector Trajectory: Raw vs FracDiff(d*=0.25) vs Return(d=1)", fontsize=12, fontweight="bold", pad=10)
    ax4.set_xlabel("Date", fontsize=10, fontweight="bold")
    ax4.set_ylabel("Standardized Trajectory (Z-Score)", fontsize=10, fontweight="bold")
    ax4.legend(loc="upper left", frameon=True, framealpha=0.9, fontsize=9)
    ax4.grid(True, linestyle=":", alpha=0.6)

    plt.tight_layout()
    plt.savefig(OUT_IMG_TEST, dpi=300)
    if os.path.exists(ARTIFACT_DIR):
        shutil.copy(OUT_IMG_TEST, OUT_IMG_ARTIFACT)
        print(f"[OK] Saved to Artifact: {OUT_IMG_ARTIFACT}")
    print(f"[OK] Saved to: {OUT_IMG_TEST}")
    plt.close()


if __name__ == "__main__":
    generate_dashboard()
