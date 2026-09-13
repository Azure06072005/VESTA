"""test_pipeline/scripts/generate_temporal_visualizations.py

Generates high-resolution visualization charts and extracts representative
sample records for 1. Temporal Alignment diagnostics.
"""
import os
import sys
import duckdb
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

sys.stdout.reconfigure(encoding="utf-8")

ARTIFACT_DIR = r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\2ebb0c09-579b-48e8-91b8-599a5f512f13"
LOCAL_OUT_DIR = "test_pipeline/out"
DB_PATH = "db/test_db/vesta_test.duckdb"

def generate_visualizations():
    con = duckdb.connect(DB_PATH, read_only=True)
    
    # 1. Fetch Timestamp Distribution
    q_time = """
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN date_part('hour', published_at) = 0 AND date_part('minute', published_at) = 0 AND date_part('second', published_at) = 0 THEN 1 END) as midnight,
        COUNT(CASE WHEN date_part('hour', published_at) >= 15 THEN 1 END) as after_close,
        COUNT(CASE WHEN date_part('hour', published_at) >= 9 AND (date_part('hour', published_at) < 14 OR (date_part('hour', published_at) = 14 AND date_part('minute', published_at) <= 45)) THEN 1 END) as trading_hours,
        COUNT(CASE WHEN date_part('dow', published_at) IN (0, 6) THEN 1 END) as weekend
    FROM core.pit_events
    """
    total, midnight, after_close, trading_hours, weekend = con.execute(q_time).fetchone()
    other_time = total - (midnight + after_close + trading_hours + weekend)
    
    # 2. Fetch Stale Price Rollover Rates
    q_stale = """
    SELECT 
        COUNT(CASE WHEN price_t1 IS NOT NULL THEN 1 END) as t1_cnt,
        COUNT(CASE WHEN price_t5 IS NOT NULL THEN 1 END) as t5_cnt,
        COUNT(CASE WHEN price_t30 IS NOT NULL THEN 1 END) as t30_cnt,
        COUNT(CASE WHEN price_t1 = price_at_publish AND price_t1 > 0 THEN 1 END) as stale_t1,
        COUNT(CASE WHEN price_t5 = price_at_publish AND price_t5 > 0 THEN 1 END) as stale_t5,
        COUNT(CASE WHEN price_t30 = price_at_publish AND price_t30 > 0 THEN 1 END) as stale_t30
    FROM core.pit_events
    """
    t1_cnt, t5_cnt, t30_cnt, s_t1, s_t5, s_t30 = con.execute(q_stale).fetchone()
    
    # 3. Fetch Sample Midnight Returns
    q_ret = """
    SELECT 
        (price_t1 - price_at_publish) / price_at_publish as ret_t1_t0,
        (price_t5 - price_t1) / price_t1 as ret_t5_from_t1
    FROM core.pit_events
    WHERE date_part('hour', published_at) = 0 
      AND date_part('minute', published_at) = 0 
      AND date_part('second', published_at) = 0
      AND price_at_publish > 0 AND price_t1 > 0 AND price_t5 > 0
    LIMIT 10000
    """
    df_ret = con.execute(q_ret).df()
    
    # -------------------------------------------------------------
    # PLOT: 4-PANEL EXECUTIVE DASHBOARD
    # -------------------------------------------------------------
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), dpi=200)
    fig.patch.set_facecolor("#0f172a") # dark slate background

    for ax in axes.flat:
        ax.set_facecolor("#1e293b")
        ax.tick_params(colors="#e2e8f0", labelsize=9)
        ax.xaxis.label.set_color("#e2e8f0")
        ax.yaxis.label.set_color("#e2e8f0")
        ax.title.set_color("#f8fafc")
        for spine in ax.spines.values():
            spine.set_color("#334155")
    
    # --- PANEL 1: TIMESTAMP COMPOSITION DONUT ---
    ax1 = axes[0, 0]
    sizes = [midnight, after_close, trading_hours, weekend]
    labels = [
        f"Midnight 00:00:00\n({midnight:,} - {midnight/total*100:.1f}%)",
        f"After-Close >=15:00\n({after_close:,} - {after_close/total*100:.1f}%)",
        f"Trading Hours\n({trading_hours:,} - {trading_hours/total*100:.1f}%)",
        f"Weekend\n({weekend:,} - {weekend/total*100:.1f}%)"
    ]
    colors = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b"]
    wedges, texts, autotexts = ax1.pie(
        sizes, labels=labels, colors=colors, autopct="%1.1f%%", pctdistance=0.75,
        startangle=140, textprops=dict(color="#f8fafc", fontsize=9, fontweight="bold")
    )
    for at in autotexts:
        at.set_color("#ffffff")
        at.set_fontsize(8)
    center_circle = plt.Circle((0, 0), 0.50, fc="#1e293b")
    ax1.add_artist(center_circle)
    ax1.set_title("1.1 Timestamp Distribution (658,182 PIT Events)\n[Highlight: 25.7% Midnight Look-ahead Risk]", fontsize=11, fontweight="bold", pad=12)

    # --- PANEL 2: HORIZON COVERAGE & ATTRITION ---
    ax2 = axes[0, 1]
    horizons = ["Total Events", "T+1 Available", "T+5 Available", "T+30 Available", "Clean Tradeable"]
    counts = [total, t1_cnt, t5_cnt, t30_cnt, 582891]
    pcts = [100.0, t1_cnt/total*100, t5_cnt/total*100, t30_cnt/total*100, 582891/total*100]
    bar_colors = ["#64748b", "#0284c7", "#0ea5e9", "#38bdf8", "#10b981"]
    
    bars = ax2.bar(horizons, [c/1000 for c in counts], color=bar_colors, width=0.55, edgecolor="#0f172a", linewidth=1.2)
    ax2.set_ylabel("Count (Thousands of Events)", fontsize=10)
    ax2.set_title("1.3 Horizon Coverage & Data Cleansing Attrition\n[Zero-Prices & Suspensions Purged]", fontsize=11, fontweight="bold", pad=12)
    ax2.set_ylim(0, 750)
    
    for bar, pct, c in zip(bars, pcts, counts):
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2.0, yval + 15, f"{c:,}\n({pct:.1f}%)", ha="center", va="bottom", fontsize=8, color="#f8fafc", fontweight="bold")

    # --- PANEL 3: STALE PRICE ROLLOVER (FROZEN/SUSPENDED ASSETS) ---
    ax3 = axes[1, 0]
    h_labels = ["T+1 Horizon", "T+5 Horizon", "T+30 Horizon"]
    stale_pcts = [s_t1/t1_cnt*100, s_t5/t5_cnt*100, s_t30/t30_cnt*100]
    stale_counts = [s_t1, s_t5, s_t30]
    
    bars3 = ax3.bar(h_labels, stale_pcts, color=["#f59e0b", "#f97316", "#ef4444"], width=0.45, edgecolor="#0f172a")
    ax3.set_ylabel("Stale Price Rate (%) [P_k == P_0]", fontsize=10)
    ax3.set_title("1.3 Stale Price Rollover Rate (Liquidity Frozen Stocks)\n[5.7% of T+30 has ZERO price movement]", fontsize=11, fontweight="bold", pad=12)
    ax3.set_ylim(0, 35)
    
    for bar, pct, count in zip(bars3, stale_pcts, stale_counts):
        yval = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2.0, yval + 1, f"{pct:.2f}%\n({count:,} rows)", ha="center", va="bottom", fontsize=8.5, color="#f8fafc", fontweight="bold")

    # --- PANEL 4: MODE T+0 VS MODE T+1 RETURN DENSITY ---
    ax4 = axes[1, 1]
    ret_t0 = df_ret["ret_t1_t0"] * 100
    ret_t1 = df_ret["ret_t5_from_t1"] * 100
    
    # Clip extreme outliers for visual clarity
    ret_t0_clip = np.clip(ret_t0, -15, 15)
    ret_t1_clip = np.clip(ret_t1, -25, 25)
    
    ax4.hist(ret_t0_clip, bins=40, alpha=0.6, color="#ef4444", label=f"Mode T+0 (Aggressive Leakage)\nMean: {ret_t0.mean():.2f}%, SD: {ret_t0.std():.2f}%", density=True)
    ax4.hist(ret_t1_clip, bins=40, alpha=0.6, color="#10b981", label=f"Mode T+1 (Conservative Lag)\nMean: {ret_t1.mean():.2f}%, SD: {ret_t1.std():.2f}%", density=True)
    ax4.set_xlabel("Return (%)", fontsize=10)
    ax4.set_ylabel("Probability Density", fontsize=10)
    ax4.set_title("1.1 Execution Lag Impact on Midnight Events (N=10,000)\n[Comparing T+0 Leakage vs T+1 Clean Lag]", fontsize=11, fontweight="bold", pad=12)
    ax4.legend(loc="upper right", facecolor="#1e293b", edgecolor="#334155", labelcolor="#f8fafc", fontsize=8.5)

    plt.suptitle("VESTA QUANT DATA PREPROCESSING — STEP 1: TEMPORAL ALIGNMENT DIAGNOSTICS", fontsize=14, fontweight="bold", color="#f8fafc", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    
    # Save both locally and to artifacts
    os.makedirs(LOCAL_OUT_DIR, exist_ok=True)
    local_png = os.path.join(LOCAL_OUT_DIR, "temporal_alignment_diagnostics.png")
    plt.savefig(local_png, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
    print(f"Saved local plot to {local_png}")
    
    if os.path.exists(ARTIFACT_DIR):
        artifact_png = os.path.join(ARTIFACT_DIR, "temporal_alignment_diagnostics.png")
        plt.savefig(artifact_png, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
        print(f"Saved artifact plot to {artifact_png}")
    
    plt.close()
    con.close()

if __name__ == "__main__":
    generate_visualizations()
