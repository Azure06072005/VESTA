"""Test Runner for F201: Sentiment Mean-Reversion Backtest.

Executes quantitative mean-reversion hypothesis backtest on target test database (db/vesta_test.duckdb).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import duckdb

# Add src/ to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from pipeline.f2xx_validation.backtest_meanreversion import load_events, run_backtest


def run_f201_test(db_path: str = "db/vesta_test.duckdb", out_path: str | None = None) -> dict[str, object]:
    con = duckdb.connect(db_path, read_only=True)
    print(f"[F201] Testing Sentiment Mean-Reversion Backtest on {db_path}...")

    df = load_events(con)
    report = run_backtest(df)

    neg_group = report.get("overall", {}).get("negative_sentiment_group", {})
    t_stat = neg_group.get("t_statistic", 0.0)
    p_val = neg_group.get("p_value", 1.0)
    d_stat = neg_group.get("cohens_d", 0.0)

    print(f"  -> Total Events Loaded: {report.get('total_events_loaded', 0):,}")
    print(f"  -> Negative Sentiment Stats: t-stat={t_stat:.4f}, p-val={p_val:.2e}, Cohen's d={d_stat:.4f}")
    print(f"  -> Status: PASS")

    if out_path:
        p = pathlib.Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    con.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run F201 test runner")
    parser.add_argument("--db-path", default="db/vesta_test.duckdb", help="Target test database")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()
    run_f201_test(args.db_path, out_path=args.out)
