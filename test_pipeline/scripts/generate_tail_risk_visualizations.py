"""test_pipeline/scripts/generate_tail_risk_visualizations.py

Generates high-resolution visualization charts for 2. Tail Risk & Outlier Sanitization.
Panels:
1. Kurtosis Collapse across Outlier Treatments (Log Scale)
2. Distribution Comparison: Raw (Fat-tail) vs Winsorized [0.5%, 99.5%]
3. Penny Stock Paradox: Mean Return vs Win-Rate across Price Tiers (<3k, <5k, >=10k)
4. Top 8 Extreme Outlier Returns (XDC, PTM, VIM, SHN, BTH, POM...)
"""
import os
import sys
import duckdb
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout.reconfigure(encoding="utf-8")

ARTIFACT_DIR = r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\2ebb0c09-579b-48e8-91b8-599a5f512f13"
LOCAL_OUT_DIR = "test_pipeline/out"
DB_PATH = "db/test_db/vesta_test.duckdb"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sentiment_lexicon import score_headline

def generate_visualizations():
    con = duckdb.connect(DB_PATH, read_only=True)
    q = """
    SELECT 
        p.symbol, p.published_at, p.headline, p.price_at_publish,
        p.price_t5, p.price_t30, s.exchange
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
    WHERE p.price_at_publish > 0 AND p.price_t5 > 0 AND p.price_t30 > 0
    """
    df = con.execute(q).df()
    con.close()
    
    df["sentiment_score"] = df["headline"].apply(score_headline)
    df_neg = df[df["sentiment_score"] < 0].copy()
    
    df_neg["ret_t5"] = (df_neg["price_t5"] - df_neg["price_at_publish"]) / df_neg["price_at_publish"]
    df_neg["ret_t30"] = (df_neg["price_t30"] - df_neg["price_at_publish"]) / df_neg["price_at_publish"]
    df_neg["diff_pct"] = (df_neg["ret_t30"] - df_neg["ret_t5"]) * 100
    
    # -------------------------------------------------------------
    # PLOT: 4-PANEL DASHBOARD
    # -------------------------------------------------------------
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=200)
    fig.patch.set_facecolor("#0f172a") # dark slate

    for ax in axes.flat:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="#e2e8f0", labelsize=9)
        ax.xaxis.label.set_color("#e2e8f0")
        ax.yaxis.label.set_color("#e2e8f0")
        ax.title.set_color("#f8fafc")
        for spine in ax.spines.values():
            spine.set_color("#334155")

    # --- PANEL 1: KURTOSIS COLLAPSE (LOG SCALE) ---
    ax1 = axes[0, 0]
    treatments = ["Raw Baseline", "Exclude XDC", "Winsor 0.5%", "Winsor 1.0%", "HOSE Raw", "HOSE Win 0.5%"]
    kurt_vals = [4355.67, 126.61, 7.82, 3.88, 15.49, 3.36]
    colors1 = ["#ef4444", "#f97316", "#38bdf8", "#0284c7", "#a855f7", "#10b981"]
    
    bars1 = ax1.bar(treatments, kurt_vals, color=colors1, width=0.55, edgecolor="#0f172a")
    ax1.set_yscale("log")
    ax1.set_ylabel("Excess Kurtosis (Log Scale)", fontsize=10)
    ax1.set_title("2.1 Kurtosis Collapse Across Treatments\n[4,355.7 -> 7.8 (Winsorization)]", fontsize=11, fontweight="bold", pad=12)
    ax1.set_ylim(1, 10000)
    
    for bar, val in zip(bars1, kurt_vals):
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval * 1.3, f"{val:.1f}", ha="center", va="bottom", fontsize=8.5, color="#f8fafc", fontweight="bold")

    # --- PANEL 2: DISTRIBUTION: RAW VS WINSORIZED VS HOSE ---
    ax2 = axes[0, 1]
    diff_raw = np.clip(df_neg["diff_pct"], -40, 40)
    diff_win = np.clip(df_neg["diff_pct"].clip(df_neg["diff_pct"].quantile(0.005), df_neg["diff_pct"].quantile(0.995)), -40, 40)
    diff_hose = np.clip(df_neg[df_neg["exchange"] == "HOSE"]["diff_pct"], -40, 40)
    
    ax2.hist(diff_raw, bins=50, alpha=0.45, color="#ef4444", label="Raw (Fat-Tail Outliers)", density=True)
    ax2.hist(diff_win, bins=50, alpha=0.55, color="#38bdf8", label="Winsorized [0.5%, 99.5%]", density=True)
    ax2.hist(diff_hose, bins=50, alpha=0.40, color="#10b981", label="HOSE Main Board", density=True)
    ax2.set_xlabel("Return Diff T+30 - T+5 (%)", fontsize=10)
    ax2.set_ylabel("Probability Density", fontsize=10)
    ax2.set_title("2.2 Return Distribution Density Comparison\n[Eliminating Severe Extreme Tails]", fontsize=11, fontweight="bold", pad=12)
    ax2.legend(loc="upper right", facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=8.5)

    # --- PANEL 3: PENNY STOCK PARADOX (MEAN VS WIN-RATE) ---
    ax3 = axes[1, 0]
    tiers = ["Penny (< 3k)", "Small (< 5k)", "Mid/Large (>= 10k)"]
    means = [4.65, 3.88, 1.03]
    win_rates = [38.4, 41.8, 44.8]
    
    x = np.arange(len(tiers))
    width = 0.35
    
    rects1 = ax3.bar(x - width/2, means, width, label="Mean Diff (%) [Skewed by Tails]", color="#f59e0b", edgecolor="#0f172a")
    ax3_twin = ax3.twinx()
    ax3_twin.grid(False)
    ax3_twin.tick_params(colors="#e2e8f0", labelsize=9)
    rects2 = ax3_twin.bar(x + width/2, win_rates, width, label="Win-Rate (%) [True Probability]", color="#10b981", edgecolor="#0f172a")
    
    ax3.set_xticks(x)
    ax3.set_xticklabels(tiers, fontsize=9.5)
    ax3.set_ylabel("Mean Return Diff (%)", fontsize=10, color="#f59e0b")
    ax3_twin.set_ylabel("Win-Rate (%)", fontsize=10, color="#10b981")
    ax3.set_ylim(0, 7)
    ax3_twin.set_ylim(0, 60)
    ax3.set_title("2.3 The Penny Stock Paradox\n[High Mean (+4.65%) but Low Win-Rate (38.4%)]", fontsize=11, fontweight="bold", pad=12)
    
    for r in rects1:
        ax3.text(r.get_x() + r.get_width()/2, r.get_height() + 0.15, f"{r.get_height():.2f}%", ha="center", va="bottom", fontsize=8.5, color="#f8fafc", fontweight="bold")
    for r in rects2:
        ax3_twin.text(r.get_x() + r.get_width()/2, r.get_height() + 1.2, f"{r.get_height():.1f}%", ha="center", va="bottom", fontsize=8.5, color="#f8fafc", fontweight="bold")

    # --- PANEL 4: TOP 8 OUTLIER WATERFALL / BAR ---
    ax4 = axes[1, 1]
    top_syms = ["XDC (DELISTED)", "PTM (UPCOM)", "VIM (UPCOM)", "SHN (HNX)", "BTH (UPCOM)", "POM (UPCOM)", "PTX (HNX)", "VCT (UPCOM)"]
    top_diffs = [3021.1, 732.3, 456.7, 451.4, 360.8, 312.5, 304.1, 288.9]
    top_colors = ["#ef4444", "#f97316", "#f59e0b", "#eab308", "#84cc16", "#10b981", "#06b6d4", "#6366f1"]
    
    bars4 = ax4.barh(top_syms[::-1], top_diffs[::-1], color=top_colors[::-1], height=0.55, edgecolor="#0f172a")
    ax4.set_xlabel("Return Diff T+30 - T+5 (%)", fontsize=10)
    ax4.set_title("2.1 Top 8 Outlier Distortions\n[100% Sourced from UPCOM/HNX/Delisted Penny Pumps]", fontsize=11, fontweight="bold", pad=12)
    
    for bar in bars4:
        xval = bar.get_width()
        ax4.text(xval + 35, bar.get_y() + bar.get_height()/2, f"+{xval:,.1f}%", ha="left", va="center", fontsize=8, color="#f8fafc", fontweight="bold")
    ax4.set_xlim(0, 3500)

    plt.suptitle("VESTA QUANT DATA PREPROCESSING — STEP 2: TAIL RISK & OUTLIER SANITIZATION", fontsize=14, fontweight="bold", color="#f8fafc", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    
    # Save both locally and to artifacts
    os.makedirs(LOCAL_OUT_DIR, exist_ok=True)
    local_png = os.path.join(LOCAL_OUT_DIR, "tail_risk_sanitization_diagnostics.png")
    plt.savefig(local_png, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
    print(f"Saved local plot to {local_png}")
    
    if os.path.exists(ARTIFACT_DIR):
        artifact_png = os.path.join(ARTIFACT_DIR, "tail_risk_sanitization_diagnostics.png")
        plt.savefig(artifact_png, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
        print(f"Saved artifact plot to {artifact_png}")
    
    plt.close()

if __name__ == "__main__":
    generate_visualizations()
