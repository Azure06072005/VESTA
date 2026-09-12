"""
f201_robustness_check.py

Additive robustness audit for F201's mean-reversion result on core.pit_events.
Does NOT modify backtest_meanreversion.py or F201's recorded evidence in
feature_list.json -- this is a separate, additive check (track as its own
feature, e.g. F202, dependency on F201).

Addresses three open concerns flagged before F301 unblocks:
  1. The paired t-test's independence assumption is violated -- events
     cluster by symbol (some symbols contribute far more negative-sentiment
     headlines than others) and by time (news clusters around earnings /
     macro events). A cluster bootstrap (resample symbols, not events) gives
     a standard error that doesn't pretend those 15,081 events are 15,081
     independent draws.
  2. A parallel block bootstrap by calendar month checks time-clustering
     specifically (distinct from symbol-clustering).
  3. Regime heterogeneity is reported explicitly rather than only as
     isolated per-regime p-values -- so a sign-flip (e.g. 2022 crisis
     regime) is visible as a heterogeneity finding, not buried in a table.

===============================================================================
CONFIRM THESE THREE ITEMS AGAINST THE REAL backtest_meanreversion.py BEFORE
TRUSTING THIS SCRIPT'S OUTPUT -- see CONFIG section below:
  (a) NEGATIVE_SENTIMENT_PREDICATE / sentiment source
  (b) REGIME_BOUNDARIES (16-regime sourced timeline configured per DECISIONS.md)
  (c) RETURN_COLUMNS -- whether return_t5/return_t30 already exist as
      columns, or must be computed from price_at_publish/price_t5/price_t30
===============================================================================

Usage:
    python src/pipeline/f201_robustness_check.py \
        --db db/vesta.duckdb \
        --report out/f201_robustness_report.json
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# =============================================================================
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.sentiment_lexicon import score_headline

# (a) How F201 decides an event is "negative sentiment".
# Set to None to use classify_negative_from_headline directly with exact F201 sentiment_lexicon
NEGATIVE_SENTIMENT_SQL_PREDICATE = None

def classify_negative_from_headline(headline: str) -> bool:
    """Exact negative threshold matching F201 backtest_meanreversion.py."""
    if not headline or not isinstance(headline, str):
        return False
    return score_headline(headline) < 0.0

# (b) Regime boundaries -- Canonical 16-regime sourced timeline (2000-2026) per
#     DECISIONS.md (2026-09-09), superseding the placeholder 5-way split.
# scope: "GLOBAL" (event originated outside VN, VN market not the primary
# subject), "VN_DOMESTIC" (VN-specific event, no major global driver in
# this window), or "BOTH" (a global event transmitted into VN, or VN and
# global drivers overlapped in the same window).
REGIME_BOUNDARIES: list[tuple[str, str, str, str]] = [
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

# (c) Set True if return_t5/return_t30 already exist as columns on the table
#     queried below; set False to compute them here from raw prices instead.
RETURN_COLUMNS_EXIST = False

# Table to query -- adjust if F104 built a separate features table instead of
# reading core.pit_events directly.
SOURCE_TABLE = "core.pit_events"

MIN_SAMPLE_SIZE = 10  # matches F201's stated minimum for a regime to report
N_BOOT = 2000
RANDOM_SEED = 42


# =============================================================================
# Data loading
# =============================================================================

def load_events(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    if RETURN_COLUMNS_EXIST:
        cols = "symbol, published_at, headline, return_t5, return_t30"
    else:
        cols = "symbol, published_at, headline, price_at_publish, price_t5, price_t30"

    query = f"""
        SELECT {cols}
        FROM {SOURCE_TABLE}
        WHERE price_at_publish IS NOT NULL AND price_t5 IS NOT NULL AND price_t30 IS NOT NULL
    """
    df = con.execute(query).fetchdf()

    if not RETURN_COLUMNS_EXIST:
        df["return_t5"] = (df["price_t5"] - df["price_at_publish"]) / df["price_at_publish"]
        df["return_t30"] = (df["price_t30"] - df["price_at_publish"]) / df["price_at_publish"]

    if NEGATIVE_SENTIMENT_SQL_PREDICATE is not None:
        # sentiment column already classified; filter in pandas to keep this
        # script decoupled from a second SQL round-trip
        df["is_negative"] = df["sentiment"].astype(str).str.lower().eq("negative")
    else:
        df["is_negative"] = df["headline"].apply(classify_negative_from_headline)

    df["published_at"] = pd.to_datetime(df["published_at"])
    df["month"] = df["published_at"].dt.to_period("M").astype(str)
    df["diff"] = df["return_t30"] - df["return_t5"]

    return df[df["is_negative"]].dropna(subset=["diff", "symbol", "month"]).reset_index(drop=True)


# =============================================================================
# Stats helpers (no scipy dependency -- normal approximation for large n,
# which is appropriate here since every group has n > 1000)
# =============================================================================

def _norm_sf(z: float) -> float:
    """Two-sided p-value from a z/t statistic via the normal survival function."""
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))


def naive_paired_test(diff: np.ndarray) -> dict:
    n = len(diff)
    mean = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1))
    se = sd / math.sqrt(n)
    t = mean / se if se > 0 else float("nan")
    p = _norm_sf(t)
    cohens_d = mean / sd if sd > 0 else float("nan")
    return {"n": n, "mean_diff": mean, "sd": sd, "se_naive": se,
            "t_naive": t, "p_naive": p, "cohens_d": cohens_d}


def cluster_bootstrap(df: pd.DataFrame, cluster_col: str, n_boot: int, seed: int) -> dict:
    """Resample CLUSTERS (e.g. symbols or months) with replacement, not
    individual events -- this is what makes it cluster-robust rather than
    just a naive event-level bootstrap that would inherit the same
    independence assumption as the t-test."""
    rng = np.random.default_rng(seed)
    clusters = df[cluster_col].unique()
    n_clusters = len(clusters)

    grouped = {c: g["diff"].to_numpy() for c, g in df.groupby(cluster_col)}
    boot_means = np.empty(n_boot)

    for b in range(n_boot):
        sampled_clusters = rng.choice(clusters, size=n_clusters, replace=True)
        pooled = np.concatenate([grouped[c] for c in sampled_clusters])
        boot_means[b] = pooled.mean()

    se_boot = float(np.std(boot_means, ddof=1))
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    point_estimate = float(df["diff"].mean())
    z = point_estimate / se_boot if se_boot > 0 else float("nan")
    p_boot = _norm_sf(z)

    return {
        "n_clusters": int(n_clusters),
        "n_events": int(len(df)),
        "mean_diff": point_estimate,
        "se_cluster_bootstrap": se_boot,
        "ci_95_low": float(ci_low),
        "ci_95_high": float(ci_high),
        "z_cluster": z,
        "p_cluster": p_boot,
        "ci_excludes_zero": bool(ci_low > 0 or ci_high < 0),
    }


def regime_breakdown(df: pd.DataFrame, boundaries: list[tuple[str, str, str, str]],
                      n_boot: int, seed: int) -> list[dict]:
    results = []
    for name, start, end, scope in boundaries:
        mask = (df["published_at"] >= start) & (df["published_at"] <= end)
        sub = df.loc[mask]
        if len(sub) < MIN_SAMPLE_SIZE:
            results.append({"regime": name, "scope": scope,
                             "status": "insufficient_data", "n": int(len(sub))})
            continue
        naive = naive_paired_test(sub["diff"].to_numpy())
        n_symbols = sub["symbol"].nunique()
        if n_symbols >= 2:
            cluster = cluster_bootstrap(sub, "symbol", n_boot, seed)
        else:
            cluster = {"status": "too_few_symbols_for_cluster_bootstrap", "n_symbols": int(n_symbols)}
        results.append({"regime": name, "scope": scope, "date_range": [start, end],
                         "naive": naive, "cluster_robust": cluster})
    return results
    

def regime_heterogeneity_flag(regime_results: list[dict]) -> dict:
    """Not a formal interaction test (would need statsmodels / a real
    regression with cluster-robust SEs) -- just makes a sign-flip or wildly
    divergent effect size impossible to miss in the printed/JSON output."""
    signs = []
    for r in regime_results:
        if r.get("status") == "insufficient_data":
            continue
        d = r["naive"]["mean_diff"]
        signs.append((r["regime"], "positive" if d > 0 else "negative", r["naive"]["mean_diff"]))
    flips = len({s for _, s, _ in signs}) > 1
    return {"regimes_compared": signs, "sign_flip_detected": flips}


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="db/vesta.duckdb")
    parser.add_argument("--report", default="out/f201_robustness_report.json")
    args = parser.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    df = load_events(con)

    print(f"Loaded {len(df)} negative-sentiment events across "
          f"{df['symbol'].nunique()} symbols, {df['month'].nunique()} months.")

    pooled_naive = naive_paired_test(df["diff"].to_numpy())
    pooled_symbol_cluster = cluster_bootstrap(df, "symbol", N_BOOT, RANDOM_SEED)
    pooled_month_cluster = cluster_bootstrap(df, "month", N_BOOT, RANDOM_SEED)
    regimes = regime_breakdown(df, REGIME_BOUNDARIES, N_BOOT, RANDOM_SEED)
    heterogeneity = regime_heterogeneity_flag(regimes)

    report = {
        "pooled_naive_paired_ttest": pooled_naive,
        "pooled_cluster_robust_by_symbol": pooled_symbol_cluster,
        "pooled_cluster_robust_by_month": pooled_month_cluster,
        "regime_breakdown": regimes,
        "regime_heterogeneity": heterogeneity,
        "config_used": {
            "negative_sentiment_predicate": NEGATIVE_SENTIMENT_SQL_PREDICATE,
            "regime_boundaries": REGIME_BOUNDARIES,
            "return_columns_precomputed": RETURN_COLUMNS_EXIST,
            "n_boot": N_BOOT,
            "seed": RANDOM_SEED,
        },
    }

    print(json.dumps({
        "pooled_naive": pooled_naive,
        "pooled_cluster_robust_by_symbol": pooled_symbol_cluster,
        "regime_heterogeneity": heterogeneity,
    }, indent=2))

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2, default=str))
    print(f"\nFull report written to {args.report}")


if __name__ == "__main__":
    main()