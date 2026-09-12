"""
eda_visualization.py — Comprehensive Visual EDA across VESTA Datasets.

Two distinct visualization tiers:
  Tier 1: Market-level overview (cross-symbol macro, breadth, news, sectors, regimes)
  Tier 2: Single-company deep dive (OHLCV candlesticks, event overlays, ratios, return distributions)

Outputs publication-ready static figures (PNG, 150 DPI) to out/figures/.
Supports CLI parameters for target equity, date ranges, and DuckDB database path.

Usage:
    python src/pipeline/ml/data_validation/eda_visualization.py --db db/vesta.duckdb --symbol FPT
    # or fallback to backup if database is locked:
    python src/pipeline/ml/data_validation/eda_visualization.py --db db/vesta_latest_backup.duckdb --symbol FPT
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd
import seaborn as sns

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Configure global publication styling
plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "figure.figsize": (12, 6),
    "figure.dpi": 150,
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "font.family": "sans-serif",
})

PALETTE = ["#2b5c8f", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d"]

# Sourced 16-Regime Timeline (2000-2026) from DECISIONS.md (2026-09-09)
REGIME_BOUNDARIES = [
    ("dotcom_bubble_crash_vn",       "2000-07-28", "2002-10-31", "BOTH"),
    ("post_bubble_consolidation",    "2002-11-01", "2005-12-31", "VN_DOMESTIC"),
    ("pre_gfc_bull_run",             "2006-01-01", "2007-03-31", "VN_DOMESTIC"),
    ("gfc_crash",                    "2007-04-01", "2009-02-28", "BOTH"),
    ("post_gfc_recovery",            "2009-03-01", "2011-06-30", "BOTH"),
    ("euro_debt_crisis_overlay",     "2011-07-01", "2012-12-31", "GLOBAL"),
    ("steady_growth",                "2013-01-01", "2015-12-31", "BOTH"),
    ("bull_run_2016_2018",           "2016-01-01", "2018-03-31", "VN_DOMESTIC"),
    ("bear_market_2018_2019",        "2018-04-01", "2019-12-31", "BOTH"),
    ("covid_crash",                  "2020-01-01", "2020-04-30", "BOTH"),
    ("covid_recovery_rally",         "2020-05-01", "2022-01-31", "BOTH"),
    ("real_estate_bond_crisis_2022", "2022-02-01", "2022-12-31", "BOTH"),
    ("recovery_2023_2024",           "2023-01-01", "2024-12-31", "VN_DOMESTIC"),
    ("tariff_shock_ftse_rally_2025", "2025-01-01", "2025-10-19", "BOTH"),
    ("ftse_upgrade_correction",      "2025-10-20", "2025-12-31", "VN_DOMESTIC"),
    ("pre_upgrade_run_2026",         "2026-01-01", "2026-09-08", "BOTH"),
]


# =============================================================================
# Tier 1: Market-Level Visualizations (Cross-Symbol)
# =============================================================================

def market_trend_with_regimes(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Equal-weighted daily average close proxy with shaded regime boundaries."""
    print("  Generating: Market trend with sourced regime shading...")
    df = con.execute("""
        SELECT date, AVG(close) AS avg_close, COUNT(DISTINCT symbol) AS n_symbols
        FROM core.market_ohlcv_daily
        GROUP BY date ORDER BY date
    """).fetchdf()
    df["date"] = pd.to_datetime(df["date"])

    fig, ax1 = plt.subplots(figsize=(16, 7))
    line1 = ax1.plot(df["date"], df["avg_close"], color="#1f77b4", linewidth=1.5, label="Equal-Weighted Avg Close (VND '000)")
    ax1.set_ylabel("Equal-Weighted Average Close Price (VND)", color="#1f77b4", fontweight="bold")
    ax1.set_title("Vietnam Equity Market Trend (2000–2026) Across 16 Sourced Regimes", pad=15)

    ax2 = ax1.twinx()
    line2 = ax2.plot(df["date"], df["n_symbols"], color="#7f7f7f", linewidth=1.0, linestyle="--", alpha=0.6, label="Listed Symbols Count")
    ax2.set_ylabel("Active Symbols Count", color="#7f7f7f")
    ax2.grid(False)

    # Shade the 16 regimes
    regime_colors = ["#bdd7e7", "#bae4b3", "#fcae91", "#cbc9e2", "#fee6ce", "#d9d9d9"]
    for i, (name, start, end, scope) in enumerate(REGIME_BOUNDARIES):
        s_date = pd.to_datetime(start)
        e_date = pd.to_datetime(end)
        color = regime_colors[i % len(regime_colors)]
        ax1.axvspan(s_date, e_date, color=color, alpha=0.25)
        # Label major regimes
        mid_date = s_date + (e_date - s_date) / 2
        ax1.text(mid_date, ax1.get_ylim()[1] * 0.96, f"{i+1}", horizontalalignment="center",
                 fontsize=8, fontweight="bold", color="#333333", alpha=0.8)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left", frameon=True)
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    plt.tight_layout()
    out_file = out_dir / "market_trend_regimes.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def sector_performance_heatmap(con: duckdb.DuckDBPyConnection, out_dir: Path, year: int = 2025) -> None:
    """Average annual equity return by ICB sector."""
    print(f"  Generating: Sector performance breakdown for {year}...")
    df = con.execute(f"""
        WITH yearly AS (
          SELECT o.symbol, d.industry_name,
                 FIRST(o.close ORDER BY o.date) AS open_px,
                 LAST(o.close ORDER BY o.date) AS close_px
          FROM core.market_ohlcv_daily o
          JOIN core.dim_symbol d ON o.symbol = d.symbol
          WHERE EXTRACT(YEAR FROM o.date) = {year} AND o.close > 0
          GROUP BY o.symbol, d.industry_name
        )
        SELECT COALESCE(industry_name, 'Unclassified') AS industry_name,
               COUNT(*) AS symbol_count,
               AVG((close_px - open_px) / NULLIF(open_px, 0)) AS avg_return,
               MEDIAN((close_px - open_px) / NULLIF(open_px, 0)) AS median_return
        FROM yearly
        GROUP BY industry_name
        HAVING COUNT(*) >= 3
        ORDER BY avg_return DESC
    """).fetchdf()

    fig, ax = plt.subplots(figsize=(10, max(5, len(df) * 0.42)))
    colors = ["#2ca02c" if r >= 0 else "#d62728" for r in df["avg_return"]]
    y_pos = np.arange(len(df))
    bars = ax.barh(y_pos, df["avg_return"] * 100, color=colors, alpha=0.85, edgecolor="none")

    ax.set_yticks(y_pos)
    ax.set_yticklabels([f"{row['industry_name']} (n={row['symbol_count']})" for _, row in df.iterrows()])
    ax.invert_yaxis()
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Average Annual Return (%)")
    ax.set_title(f"Vietnam Equity Sector Performance ({year})", pad=12)

    # Bar value labels
    for bar in bars:
        width = bar.get_width()
        ha = "left" if width >= 0 else "right"
        offset = 1.0 if width >= 0 else -1.0
        ax.text(width + offset, bar.get_y() + bar.get_height()/2, f"{width:.1f}%",
                va="center", ha=ha, fontsize=9, fontweight="bold")

    plt.tight_layout()
    out_file = out_dir / f"sector_performance_{year}.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def market_breadth(con: duckdb.DuckDBPyConnection, out_dir: Path, start: str = "2024-01-01", end: str = "2026-09-08") -> None:
    """Daily market breadth (advancers, decliners, unchanged) and net breadth ratio."""
    print("  Generating: Market breadth & participation dynamics...")
    df = con.execute(f"""
        SELECT date,
               COUNT(*) FILTER (WHERE close > open) AS advancers,
               COUNT(*) FILTER (WHERE close < open) AS decliners,
               COUNT(*) FILTER (WHERE close = open) AS unchanged
        FROM core.market_ohlcv_daily
        WHERE date BETWEEN '{start}' AND '{end}'
        GROUP BY date ORDER BY date
    """).fetchdf()
    df["date"] = pd.to_datetime(df["date"])
    df["total"] = df["advancers"] + df["decliners"] + df["unchanged"]
    df["net_breadth"] = (df["advancers"] - df["decliners"]) / df["total"]
    df["net_breadth_ma20"] = df["net_breadth"].rolling(window=20, min_periods=5).mean()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, gridspec_kw={"height_ratios": [2.5, 1.2]})

    # Stacked area for counts
    ax1.plot(df["date"], df["advancers"], color="#2ca02c", label="Advancers (Close > Open)", linewidth=1.2)
    ax1.plot(df["date"], df["decliners"], color="#d62728", label="Decliners (Close < Open)", linewidth=1.2)
    ax1.plot(df["date"], df["unchanged"], color="#7f7f7f", label="Unchanged", linewidth=0.8, alpha=0.7)
    ax1.set_ylabel("Daily Number of Symbols")
    ax1.set_title(f"Market Breadth: Advancers vs. Decliners ({start} to {end})")
    ax1.legend(loc="upper left")

    # Net breadth oscillator
    ax2.bar(df["date"], df["net_breadth"], color=np.where(df["net_breadth"] >= 0, "#2ca02c", "#d62728"),
            alpha=0.5, width=1.0, label="Daily Net Breadth")
    ax2.plot(df["date"], df["net_breadth_ma20"], color="#1f77b4", linewidth=1.8, label="20-day SMA Net Breadth")
    ax2.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax2.set_ylabel("Net Ratio")
    ax2.set_ylim(-0.8, 0.8)
    ax2.legend(loc="upper left")

    fig.autofmt_xdate()
    plt.tight_layout()
    out_file = out_dir / "market_breadth.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def news_volume_timeline(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Monthly article volume over time across core.news and core.macro_policy."""
    print("  Generating: News & Macro regulatory volume timeline...")
    df_news = con.execute("""
        SELECT DATE_TRUNC('month', published_at) AS month_dt,
               source, COUNT(*) AS count
        FROM core.news
        GROUP BY month_dt, source
        ORDER BY month_dt
    """).fetchdf()

    df_macro = con.execute("""
        SELECT DATE_TRUNC('month', published_at) AS month_dt,
               'macro_policy' AS source, COUNT(*) AS count
        FROM core.macro_policy
        GROUP BY month_dt
        ORDER BY month_dt
    """).fetchdf()

    combined = pd.concat([df_news, df_macro], ignore_index=True)
    combined["month_dt"] = pd.to_datetime(combined["month_dt"])
    pivot = combined.pivot_table(index="month_dt", columns="source", values="count", fill_value=0)

    fig, ax = plt.subplots(figsize=(14, 6))
    pivot.plot(kind="area", stacked=True, ax=ax, alpha=0.8, colormap="tab10")
    ax.set_title("VESTA Monthly Crawled News & Policy Volume (Temporal Depth Profile)")
    ax.set_ylabel("Number of Articles / Dispatches")
    ax.set_xlabel("Publication Month")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(title="Source Stream", loc="upper left")
    fig.autofmt_xdate()
    plt.tight_layout()
    out_file = out_dir / "news_volume_timeline.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def corporate_events_seasonality(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Corporate events seasonality heatmap (Month of Year vs Event Type)."""
    print("  Generating: Corporate events seasonality heatmap...")
    df = con.execute("""
        SELECT EXTRACT(MONTH FROM event_date) AS month,
               event_type, COUNT(*) AS event_count
        FROM core.corporate_events
        WHERE event_date IS NOT NULL
        GROUP BY month, event_type
        ORDER BY month, event_type
    """).fetchdf()

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    df["month_name"] = df["month"].apply(lambda m: month_names[int(m) - 1])
    pivot = df.pivot_table(index="event_type", columns="month_name", values="event_count", fill_value=0)
    pivot = pivot.reindex(columns=month_names).fillna(0).astype(int)

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.heatmap(pivot, annot=True, fmt="d", cmap="YlGnBu", cbar=True, ax=ax, linewidths=0.5)
    ax.set_title("Vietnam Corporate Events Seasonality (Count by Month & Type)")
    ax.set_xlabel("Month of Year")
    ax.set_ylabel("Corporate Event Type")
    plt.tight_layout()
    out_file = out_dir / "corporate_events_seasonality.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def crawl_health_dashboard(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Operational status breakdown by dataset from meta.crawl_progress."""
    print("  Generating: Crawl health & operational status dashboard...")
    df = con.execute("""
        SELECT dataset_name, status, COUNT(*) AS count
        FROM meta.crawl_progress
        GROUP BY dataset_name, status
        ORDER BY dataset_name, count DESC
    """).fetchdf()

    pivot = df.pivot_table(index="dataset_name", columns="status", values="count", fill_value=0)
    fig, ax = plt.subplots(figsize=(10, 5))
    pivot.plot(kind="barh", stacked=True, ax=ax,
               color={"success": "#2ca02c", "failed": "#d62728", "empty": "#ff7f0e", "pending": "#1f77b4"},
               alpha=0.85)
    ax.set_title("VESTA Pipeline Crawl Progress Health (by Target Dataset)")
    ax.set_xlabel("Total Symbols Processed")
    ax.set_ylabel("Crawler Dataset")
    ax.legend(title="Execution Status", loc="lower right")
    plt.tight_layout()
    out_file = out_dir / "crawl_health_dashboard.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def market_indices_5y_comparison(con: duckdb.DuckDBPyConnection, out_dir: Path,
                                  start: str = "2021-09-01", end: str = "2026-09-08") -> None:
    """5-Year Comparative Market Index Analysis: VNINDEX vs HNX-INDEX (2021-2026).
    
    Pulls official benchmark series from core.market_index_daily.
    Generates a 3-panel publication-grade figure:
      1. Normalized Performance (Base 100) with shaded market regimes.
      2. Maximum Drawdown trajectory (% off rolling peak).
      3. Rolling 60-day correlation between HOSE (VNINDEX) and HNX.
    """
    print(f"  Generating: VNINDEX vs HNX-INDEX 5-year comparison ({start} to {end})...")
    df = con.execute(f"""
        SELECT date, index_code, close, volume
        FROM core.market_index_daily
        WHERE index_code IN ('VNINDEX', 'HNX-INDEX')
          AND date BETWEEN '{start}' AND '{end}'
        ORDER BY date, index_code
    """).fetchdf()

    if df.empty:
        print("    [SKIP] No index rows found in core.market_index_daily.")
        return

    df["date"] = pd.to_datetime(df["date"])
    pivot_close = df.pivot(index="date", columns="index_code", values="close").dropna()

    if "VNINDEX" not in pivot_close or "HNX-INDEX" not in pivot_close:
        print("    [SKIP] Missing VNINDEX or HNX-INDEX series in result.")
        return

    # 1. Base 100 normalization
    norm_vn = (pivot_close["VNINDEX"] / pivot_close["VNINDEX"].iloc[0]) * 100
    norm_hnx = (pivot_close["HNX-INDEX"] / pivot_close["HNX-INDEX"].iloc[0]) * 100

    # 2. Drawdowns
    dd_vn = (pivot_close["VNINDEX"] / pivot_close["VNINDEX"].cummax() - 1) * 100
    dd_hnx = (pivot_close["HNX-INDEX"] / pivot_close["HNX-INDEX"].cummax() - 1) * 100

    # 3. Rolling 60-day return correlation
    ret_vn = pivot_close["VNINDEX"].pct_change()
    ret_hnx = pivot_close["HNX-INDEX"].pct_change()
    roll_corr = ret_vn.rolling(60).corr(ret_hnx)

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 10), sharex=True,
                                        gridspec_kw={"height_ratios": [2.5, 1.3, 1.2]})

    # Panel 1: Normalized Performance
    ax1.plot(pivot_close.index, norm_vn, label=f"VN-Index (HOSE) [Last: {pivot_close['VNINDEX'].iloc[-1]:,.1f}]",
             color="#1f77b4", linewidth=1.8)
    ax1.plot(pivot_close.index, norm_hnx, label=f"HNX-Index (HNX) [Last: {pivot_close['HNX-INDEX'].iloc[-1]:,.1f}]",
             color="#d95f02", linewidth=1.8)
    ax1.axhline(100, color="black", linestyle=":", linewidth=0.8, alpha=0.7)
    ax1.set_ylabel("Normalized Index (Base 100)")
    ax1.set_title("Vietnam 5-Year Benchmark Index Trajectory: VNINDEX vs. HNX-INDEX (2021–2026)", pad=12)

    # Shade regimes overlapping 2021-2026
    start_dt = pd.to_datetime(start)
    for name, r_start, r_end, scope in REGIME_BOUNDARIES:
        rs = pd.to_datetime(r_start)
        re = pd.to_datetime(r_end)
        if re >= start_dt:
            ax1.axvspan(max(rs, start_dt), re, color="#7570b3", alpha=0.08)

    ax1.legend(loc="upper left", frameon=True)

    # Panel 2: Drawdowns
    ax2.plot(pivot_close.index, dd_vn, label="VNINDEX Drawdown", color="#1f77b4", linewidth=1.2)
    ax2.plot(pivot_close.index, dd_hnx, label="HNX-INDEX Drawdown", color="#d95f02", linewidth=1.2, alpha=0.85)
    ax2.fill_between(pivot_close.index, dd_vn, 0, color="#1f77b4", alpha=0.15)
    ax2.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax2.set_ylabel("Drawdown (%)")
    ax2.legend(loc="lower left", fontsize=9)

    # Panel 3: Rolling 60-day correlation
    ax3.plot(pivot_close.index, roll_corr, label="60-Day Rolling Return Correlation", color="#2ca02c", linewidth=1.4)
    ax3.axhline(roll_corr.mean(), color="#7f7f7f", linestyle="--", linewidth=0.8,
                label=f"Mean Correlation ({roll_corr.mean():.2f})")
    ax3.set_ylabel("Correlation (r)")
    ax3.set_ylim(0.2, 1.0)
    ax3.legend(loc="lower left", fontsize=9)

    fig.autofmt_xdate()
    plt.tight_layout()
    out_file = out_dir / "vnindex_hnx_5y_comparison.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")



# =============================================================================
# Tier 2: Single-Company Deep Dive Visualizations (Parameterized by Symbol)
# =============================================================================

def company_candlestick(con: duckdb.DuckDBPyConnection, out_dir: Path, symbol: str, start: str, end: str) -> None:
    """Standard OHLCV candlestick chart with Volume and SMA(20, 50) via mplfinance."""
    print(f"  Generating: {symbol} candlestick chart ({start} to {end})...")
    df = con.execute(f"""
        SELECT date, open AS Open, high AS High, low AS Low, close AS Close, volume AS Volume
        FROM core.market_ohlcv_daily
        WHERE symbol = '{symbol}' AND date BETWEEN '{start}' AND '{end}'
        ORDER BY date
    """).fetchdf()

    if df.empty:
        print(f"    [SKIP] No OHLCV rows found for {symbol} between {start} and {end}")
        return

    df["Date"] = pd.to_datetime(df["date"])
    df.set_index("Date", inplace=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)

    out_file = out_dir / f"{symbol}_candlestick.png"
    mpf.plot(
        df,
        type="candle",
        volume=True,
        mav=(20, 50),
        style="yahoo",
        warn_too_much_data=2000,
        title=f"\n{symbol} Daily OHLCV with 20 & 50 SMA ({start} to {end})",
        savefig=dict(fname=str(out_file), dpi=150, bbox_inches="tight")
    )
    print(f"    -> Saved {out_file.name}")


def company_events_overlay(con: duckdb.DuckDBPyConnection, out_dir: Path, symbol: str, start: str, end: str) -> None:
    """Close price with corporate action and news/sentiment overlay markers."""
    print(f"  Generating: {symbol} price with corporate & news events overlay...")
    px = con.execute(f"""
        SELECT date, close FROM core.market_ohlcv_daily
        WHERE symbol = '{symbol}' AND date BETWEEN '{start}' AND '{end}'
        ORDER BY date
    """).fetchdf()
    if px.empty:
        print(f"    [SKIP] No price data for {symbol}")
        return
    px["date"] = pd.to_datetime(px["date"])

    # Query corporate events
    events = con.execute(f"""
        SELECT event_date, event_type FROM core.corporate_events
        WHERE symbol = '{symbol}' AND event_date BETWEEN '{start}' AND '{end}'
    """).fetchdf()

    # Query news publication points
    news = con.execute(f"""
        SELECT published_at, price_at_publish, headline FROM core.pit_events
        WHERE symbol = '{symbol}' AND published_at BETWEEN '{start}' AND '{end}'
          AND price_at_publish IS NOT NULL
    """).fetchdf()

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(px["date"], px["close"], color="#2b5c8f", linewidth=1.5, label="Daily Close Price")

    # Map corporate events onto price curve
    if not events.empty:
        events["event_date"] = pd.to_datetime(events["event_date"])
        m_events = pd.merge(events, px, left_on="event_date", right_on="date", how="inner")
        if not m_events.empty:
            ax.scatter(m_events["event_date"], m_events["close"] * 1.02, color="#2ca02c",
                       marker="^", s=80, zorder=6, label="Corporate Event (Dividend / AGM)")

    # Map news occurrences
    if not news.empty:
        news["published_at"] = pd.to_datetime(news["published_at"])
        ax.scatter(news["published_at"], news["price_at_publish"], color="#d62728",
                   marker="o", s=35, alpha=0.7, zorder=5, label="PIT News Publication Event")

    ax.set_title(f"{symbol}: Price History with Point-In-Time Corporate Actions & News")
    ax.set_ylabel("Price (VND '000)")
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    plt.tight_layout()
    out_file = out_dir / f"{symbol}_events_overlay.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def fundamental_ratio_trend(con: duckdb.DuckDBPyConnection, out_dir: Path, symbol: str) -> None:
    """Quarterly fundamental valuation and profitability trajectory (PE, PB, ROE)."""
    print(f"  Generating: {symbol} fundamental valuation & ROE trajectory...")
    df = con.execute(f"""
        SELECT period_end,
               TRY_CAST(json_extract_string(data_json, 'RT_VALUE_PE') AS DOUBLE) AS pe,
               TRY_CAST(json_extract_string(data_json, 'RT_VALUE_PB') AS DOUBLE) AS pb,
               TRY_CAST(json_extract_string(data_json, 'RT_PRT_ROE') AS DOUBLE) AS roe
        FROM core.fundamentals
        WHERE symbol = '{symbol}' AND report_type = 'ratio'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY period_end ORDER BY fetched_at DESC) = 1
        ORDER BY period_end
    """).fetchdf()

    if df.empty or df["pe"].isna().all():
        print(f"    [SKIP] Insufficient ratio data for {symbol}")
        return

    df["period_end"] = pd.to_datetime(df["period_end"])
    df.dropna(subset=["pe", "pb"], how="all", inplace=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

    # PE and PB ratios
    ax1.plot(df["period_end"], df["pe"], marker="o", color="#1f77b4", linewidth=1.5, label="P/E Ratio")
    ax1.plot(df["period_end"], df["pb"], marker="s", color="#ff7f0e", linewidth=1.5, label="P/B Ratio")
    ax1.set_ylabel("Valuation Multiple (x)")
    ax1.set_title(f"{symbol}: Quarterly Valuation Multiples & Return on Equity (ROE)")
    ax1.legend(loc="upper left")

    # ROE percentage
    if "roe" in df and not df["roe"].isna().all():
        ax2.plot(df["period_end"], df["roe"] * 100, marker="^", color="#2ca02c", linewidth=1.8, label="ROE (%)")
        ax2.axhline(15, color="#7f7f7f", linestyle="--", linewidth=0.8, label="15% Benchmark")
        ax2.set_ylabel("ROE (%)")
        ax2.legend(loc="upper left")

    fig.autofmt_xdate()
    plt.tight_layout()
    out_file = out_dir / f"{symbol}_valuation_trend.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


def return_distribution_comparison(con: duckdb.DuckDBPyConnection, out_dir: Path, symbol: str) -> None:
    """Compares T+1, T+5, and T+30 post-news returns for this symbol vs. universe."""
    print(f"  Generating: {symbol} vs Universe return distributions...")
    df_sym = con.execute(f"""
        SELECT (price_t1 - price_at_publish) / NULLIF(price_at_publish, 0) AS ret_t1,
               (price_t5 - price_at_publish) / NULLIF(price_at_publish, 0) AS ret_t5,
               (price_t30 - price_at_publish) / NULLIF(price_at_publish, 0) AS ret_t30
        FROM core.pit_events
        WHERE symbol = '{symbol}' AND price_at_publish > 0
    """).fetchdf()

    df_all = con.execute(f"""
        SELECT (price_t1 - price_at_publish) / NULLIF(price_at_publish, 0) AS ret_t1,
               (price_t5 - price_at_publish) / NULLIF(price_at_publish, 0) AS ret_t5,
               (price_t30 - price_at_publish) / NULLIF(price_at_publish, 0) AS ret_t30
        FROM core.pit_events
        WHERE price_at_publish > 0
        USING SAMPLE 10000
    """).fetchdf()

    if df_sym.empty:
        print(f"    [SKIP] No PIT events for {symbol}")
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    horizons = [("ret_t1", "T+1 Return", axes[0]), ("ret_t5", "T+5 Return", axes[1]), ("ret_t30", "T+30 Return", axes[2])]

    for col, title, ax in horizons:
        # Clip extreme tails for visual clarity
        s_data = df_sym[col].dropna()
        s_data = s_data[(s_data >= -0.5) & (s_data <= 0.5)]
        u_data = df_all[col].dropna()
        u_data = u_data[(u_data >= -0.5) & (u_data <= 0.5)]

        if len(u_data) > 0:
            sns.kdeplot(u_data, ax=ax, color="#7f7f7f", fill=True, alpha=0.2, label="Universe Sample (n=10k)")
        if len(s_data) > 0:
            sns.kdeplot(s_data, ax=ax, color="#1f77b4", linewidth=2.0, label=f"{symbol} (n={len(s_data)})")

        ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel("Return")
        ax.set_ylabel("Density")
        ax.legend(loc="upper right", fontsize=8)

    plt.suptitle(f"Post-Event Return Distribution: {symbol} vs. Universe", y=1.02, fontsize=14, fontweight="bold")
    plt.tight_layout()
    out_file = out_dir / f"{symbol}_return_distributions.png"
    fig.savefig(out_file, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> Saved {out_file.name}")


# =============================================================================
# Main Entry Point
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA Comprehensive Financial Data Visualization Suite")
    parser.add_argument("--db", default="db/vesta.duckdb", help="Path to DuckDB database")
    parser.add_argument("--symbol", default="FPT", help="Ticker symbol for company deep dive")
    parser.add_argument("--start", default="2024-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-09-08", help="End date (YYYY-MM-DD)")
    parser.add_argument("--out-dir", default="out/figures", help="Directory to save static figures")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    db_path = args.db
    if not os.path.exists(db_path):
        alt = "db/vesta_latest_backup.duckdb"
        if os.path.exists(alt):
            print(f"Warning: {db_path} not found. Using {alt}.")
            db_path = alt

    print(f"Connecting to DuckDB at {db_path} (read_only=True)...")
    try:
        con = duckdb.connect(db_path, read_only=True)
    except Exception as e:
        alt = "db/vesta_latest_backup.duckdb"
        if db_path != alt and os.path.exists(alt):
            print(f"Primary DB connection failed ({e}). Falling back to {alt}...")
            con = duckdb.connect(alt, read_only=True)
        else:
            print(f"Fatal error: Could not connect to {db_path}: {e}", file=sys.stderr)
            sys.exit(1)

    print("\n--- Generating Tier 1 Visualizations (Market Overview) ---")
    market_trend_with_regimes(con, out_dir)
    sector_performance_heatmap(con, out_dir, year=2025)
    market_breadth(con, out_dir, start=args.start, end=args.end)
    news_volume_timeline(con, out_dir)
    corporate_events_seasonality(con, out_dir)
    crawl_health_dashboard(con, out_dir)
    market_indices_5y_comparison(con, out_dir, start="2021-09-01", end=args.end)

    print(f"\n--- Generating Tier 2 Visualizations ({args.symbol} Deep Dive) ---")
    company_candlestick(con, out_dir, args.symbol, args.start, args.end)
    company_events_overlay(con, out_dir, args.symbol, args.start, args.end)
    fundamental_ratio_trend(con, out_dir, args.symbol)
    return_distribution_comparison(con, out_dir, args.symbol)

    print(f"\n[DONE] All 11 figures successfully written to {out_dir.resolve()}/")


if __name__ == "__main__":
    main()
