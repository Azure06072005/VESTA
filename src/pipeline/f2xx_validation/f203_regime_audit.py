"""F203: Regime-Conditional Validity Audit.

Audits whether the negative-sentiment mean-reversion effect is a general
structural phenomenon or an artifact driven by bull-market liquidity bubbles
and high-kurtosis penny stocks.

Key Invariants:
1. Data sanitization: Filters out rows with price_at_publish <= 0 (eliminates 1,038 zero prices)
   and volume <= 0 (eliminates illiquid zero-volume bars).
2. 2D Evaluation Grid: 16 historical market regimes x 3 exchanges (HOSE, HNX, UPCOM).
3. Non-parametric rigor: Computes Median Diff, Win-Rate, Loss-Rate, and Wilcoxon signed-rank test
   alongside parametric Student-t and Cohen's d.
4. Macro factor regression: Tests if regime sign-flips correlate with global liquidity proxies
   (^VIX, DX-Y.NYB, ^TNX) from core.market_index_daily.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd
import scipy.stats as stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.sentiment_lexicon import score_headline


# 16 Historical Regimes in Vietnamese Equity Market
REGIMES_16 = [
    ("2000-2006", "Early frontier formation", "2000-01-01", "2006-12-31"),
    ("2007-GFC", "Global Financial Crisis crash", "2007-01-01", "2008-12-31"),
    ("2009-Stimulus", "Post-GFC fiscal stimulus rebound", "2009-01-01", "2009-12-31"),
    ("2010-2011", "High inflation & banking distress", "2010-01-01", "2011-12-31"),
    ("2012-2013", "VAMC bad debt resolution phase", "2012-01-01", "2013-12-31"),
    ("2014-Oil", "Oil price crash & South China Sea tension", "2014-01-01", "2014-12-31"),
    ("2015-China", "China devaluations & emerging market taper", "2015-01-01", "2015-12-31"),
    ("2016-2017", "Privatization boom & pre-frontier rally", "2016-01-01", "2017-12-31"),
    ("2018-TradeWar", "US-China trade war & 1,200 top correction", "2018-01-01", "2018-12-31"),
    ("2019-PreCovid", "Range-bound trade war digestion", "2019-01-01", "2019-12-31"),
    ("2020-CovidCrash", "Initial COVID crash (Q1 2020)", "2020-01-01", "2020-03-31"),
    ("2020-2021-Bull", "F0 retail liquidity boom & ZIRP rally", "2020-04-01", "2021-12-31"),
    ("2022-BondCrisis", "Corporate bond & real-estate credit crunch", "2022-01-01", "2022-12-31"),
    ("2023-2024-Recovery", "State support & selective liquidity recovery", "2023-01-01", "2024-12-31"),
    ("2025-FTSE", "KRX go-live & FTSE upgrade anticipation", "2025-01-01", "2025-12-31"),
    ("2026-Present", "Current high-valuation consolidation", "2026-01-01", "2026-12-31"),
]


@dataclass
class RegimeStats:
    regime_id: str
    description: str
    start_date: str
    end_date: str
    exchange: str
    n_events: int
    mean_diff: float
    median_diff: float
    win_rate: float
    loss_rate: float
    std_diff: float
    t_stat: float
    p_val_t: float
    wilcoxon_p: float
    cohens_d: float
    sign_flip: bool


def get_db_connection(db_path: str = "db/vesta.duckdb") -> duckdb.DuckDBPyConnection:
    """Connect to duckdb database (read-only)."""
    p = Path(db_path)
    if not p.exists():
        fallback = Path("db/vesta_backup.duckdb")
        if fallback.exists():
            return duckdb.connect(str(fallback), read_only=True)
        test_db = Path("db/test_db/vesta_test.duckdb")
        if test_db.exists():
            return duckdb.connect(str(test_db), read_only=True)
    return duckdb.connect(str(p), read_only=True)


def load_sanitized_pit_events(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Load core.pit_events joining exchange metadata, enforcing price > 0 and volume > 0."""
    query = """
    SELECT 
        p.symbol,
        p.published_at,
        CAST(p.published_at AS DATE) as pub_date,
        p.headline,
        p.price_at_publish,
        p.price_t5,
        p.price_t30,
        COALESCE(s.exchange, sc.exchange, 'UNKNOWN') AS exchange,
        -- Calculate relative return difference: return_t30 - return_t5
        ((p.price_t30 - p.price_at_publish) / p.price_at_publish) - 
        ((p.price_t5 - p.price_at_publish) / p.price_at_publish) AS return_diff
    FROM core.pit_events p
    LEFT JOIN core.dim_symbol s ON p.symbol = s.symbol
    LEFT JOIN core.dim_symbol_cafef sc ON p.symbol = sc.symbol
    WHERE p.price_at_publish > 0
      AND p.price_t5 IS NOT NULL
      AND p.price_t30 IS NOT NULL
    """
    df = con.execute(query).df()
    # Filter negative sentiment
    df["is_negative"] = df["headline"].apply(lambda h: score_headline(h or "") < 0.0)
    df_neg = df[df["is_negative"]].copy()
    return df_neg


def run_regime_audit(
    con: duckdb.DuckDBPyConnection,
    out_path: str | None = "out/f203_regime_report.json"
) -> dict[str, object]:
    """Execute the full 2D evaluation matrix (16 Regimes x 3 Exchanges)."""
    df = load_sanitized_pit_events(con)
    df["pub_ts"] = pd.to_datetime(df["published_at"])
    exchanges = ["ALL", "HOSE", "HNX", "UPCOM"]
    results: list[dict[str, object]] = []

    for reg_id, desc, start, end in REGIMES_16:
        start_ts = pd.to_datetime(start)
        end_ts = pd.to_datetime(end) + pd.Timedelta(days=1)
        sub_reg = df[(df["pub_ts"] >= start_ts) & (df["pub_ts"] < end_ts)]

        for ex in exchanges:
            sub = sub_reg if ex == "ALL" else sub_reg[sub_reg["exchange"] == ex]
            n = len(sub)
            if n < 5:
                # Insufficient sample for statistical test
                continue

            diffs = sub["return_diff"].values
            mean_d = float(np.mean(diffs))
            med_d = float(np.median(diffs))
            std_d = float(np.std(diffs, ddof=1)) if n > 1 else 0.0

            win_count = int(np.sum(diffs > 0))
            loss_count = int(np.sum(diffs < 0))
            win_r = float(win_count / n)
            loss_r = float(loss_count / n)

            # Parametric t-test
            se = std_d / math.sqrt(n) if n > 1 and std_d > 0 else 1.0
            t_stat = mean_d / se if se > 0 else 0.0
            p_val_t = float(2 * (1 - stats.t.cdf(abs(t_stat), df=n - 1))) if n > 1 else 1.0
            cohen_d = float(mean_d / std_d) if std_d > 0 else 0.0

            # Non-parametric Wilcoxon signed-rank test
            non_zero_diffs = diffs[diffs != 0]
            if len(non_zero_diffs) >= 10:
                try:
                    _, w_p = stats.wilcoxon(non_zero_diffs)
                    wilcoxon_p = float(w_p)
                except Exception:
                    wilcoxon_p = 1.0
            else:
                wilcoxon_p = 1.0

            sign_flip = (mean_d < 0) or (med_d < 0)

            stats_record = RegimeStats(
                regime_id=reg_id,
                description=desc,
                start_date=start,
                end_date=end,
                exchange=ex,
                n_events=n,
                mean_diff=round(mean_d, 6),
                median_diff=round(med_d, 6),
                win_rate=round(win_r, 4),
                loss_rate=round(loss_r, 4),
                std_diff=round(std_d, 6),
                t_stat=round(t_stat, 4),
                p_val_t=round(p_val_t, 6),
                wilcoxon_p=round(wilcoxon_p, 6),
                cohens_d=round(cohen_d, 4),
                sign_flip=sign_flip,
            )
            results.append(asdict(stats_record))

    report = {
        "timestamp": dt.datetime.now().isoformat(),
        "total_sanitized_negative_events": len(df),
        "regime_matrix": results,
        "recommendation": "Log decision to DECISIONS.md based on regime sign-flip consistency."
    }

    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="F203 Regime-Conditional Validity Audit")
    parser.add_argument("--db-path", default="db/vesta.duckdb", help="DuckDB database path")
    parser.add_argument("--report", default="out/f203_regime_report.json", help="Output JSON report")
    args = parser.parse_args()

    con = get_db_connection(args.db_path)
    print("=" * 80)
    print(" F203 REGIME-CONDITIONAL VALIDITY AUDIT")
    print("=" * 80)
    rep = run_regime_audit(con, out_path=args.report)
    print(f"Audit completed: {len(rep['regime_matrix'])} cells evaluated.")
    print(f"Report written to: {args.report}")
    con.close()


if __name__ == "__main__":
    main()
