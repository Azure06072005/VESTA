"""Full-universe pilot run -- crawls EVERY symbol in core.dim_symbol
(3,446 confirmed live, see DECISIONS.md 2026-08-25 pilot double-check
entry), not just the 30-symbol scratch/pilot_symbols.txt pilot.

Reuses the exact same staged plan and functions as
scratch/staged_pilot_run.py (F002/F005/F006 synchronous -> F003/F004
background -> F101/F102 -> optional F201), differing only in:
  1. The symbol list: pulled directly from core.dim_symbol (F001 has
     already crawled this -- no separate export step needed) instead of
     a hand-curated pilot file.
  2. batch_size/delay defaults: sized for vnstock's confirmed 60
     requests/minute community-tier rate limit (see
     src/etl/batch_orchestrator.py's own docstring) at this scale,
     rather than the pilot's 30-symbol batch_size=50/delay=5s (which
     never actually triggers a delay at 30 symbols, single batch).

RATE-LIMIT SIZING (STATED ASSUMPTION, not empirically tuned against a
real multi-hour run of this exact script -- monitor `outcome['failed']`
counts on first use and widen delays if failures cluster in a way that
looks like rate-limiting rather than genuine transient network errors):
  - F002 (1 API call/symbol, confirmed via crawlers/market_ohlcv.py):
    batch_size=40, delay=50s -> ~48 req/min, 80% of the 60/min limit.
  - F006 (1 API call/symbol, confirmed via crawlers/corporate_events.py):
    same as F002.
  - F005 (4 API calls/symbol -- income_statement, cash_flow, ratio,
    balance_sheet, confirmed via crawlers/fundamentals.py's REPORT_TYPES
    loop): batch_size=10, delay=50s -> same ~48 req/min effective rate
    (10 symbols x 4 calls = 40 calls per 50s window).

ESTIMATED DURATION (STATED ASSUMPTION, back-of-envelope from the sizing
above, not a measured real-world run of this script): F002 ~72 min,
F005 ~287 min (~4.8h), F006 ~72 min, run sequentially -> roughly 7+
hours total for the synchronous stage alone, before F101/F102. This is
a MULTI-HOUR run -- start it somewhere it can run uninterrupted (or rely
on its resumability, see below, to pick up after an interruption).

RESUMABILITY: unchanged from staged_pilot_run.py -- every crawl is
routed through src/etl/batch_orchestrator.py's run_batched(), which
skips symbols already 'success'/'empty' in meta.crawl_progress. Killing
this script and re-running it later resumes rather than restarts; it
does NOT re-crawl symbols already done in an earlier invocation
(including a prior scratch/staged_pilot_run.py pilot run over the same
30-symbol subset -- those 30 symbols will be skipped here too).

F003/F004 (news) are launched in the background over the FULL universe
immediately, same rationale as the pilot script: news depth only
accumulates forward, so starting late on the full universe is
unrecoverable lost time (see DECISIONS.md 2026-08-16 item 8).
"""
from __future__ import annotations

import os
import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import migrations  # noqa: E402
from etl import batch_orchestrator as bo  # noqa: E402
from pipeline import validate_crossref  # noqa: E402
from pipeline import pit_join  # noqa: E402
from pipeline import backtest_meanreversion as bmr  # noqa: E402
from crawlers import market_ohlcv, fundamentals, corporate_events, vnstock_news, cafef_news  # noqa: E402


def run_news_stage_full_universe(con, symbols: list[str], fast: bool = False) -> None:  # type: ignore[no-untyped-def]
    """Crawl news (F003 vnstock_news and F004 cafef_news) in-process using the shared connection."""
    bs = 80 if fast else 40
    delay = 20 if fast else 50

    print(f"[full_universe_run] F003 (vnstock_news) over {len(symbols)} symbols (batch_size={bs}, delay={delay}s)...")
    outcome = bo.run_batched(con, "F003", symbols, vnstock_news.run, batch_size=bs, delay_between_batches_seconds=delay)
    print(f"[full_universe_run] F003 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")

    print(f"[full_universe_run] F004 (cafef_news) over {len(symbols)} symbols (batch_size={bs}, delay={delay}s)...")
    outcome = bo.run_batched(con, "F004", symbols, cafef_news.run, batch_size=bs, delay_between_batches_seconds=delay)
    print(f"[full_universe_run] F004 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")


def run_stock_data_stage_full_universe(con, symbols: list[str], fast: bool = False) -> None:  # type: ignore[no-untyped-def]
    """Step 2: F002 -> F005 -> F006, sequentially in-process."""
    bs_ohlcv = 80 if fast else 40
    bs_fund = 20 if fast else 10
    delay = 20 if fast else 50

    print(f"[full_universe_run] F002 (OHLCV) over {len(symbols)} symbols (batch_size={bs_ohlcv}, delay={delay}s)...")
    outcome = bo.run_batched(con, "F002", symbols, market_ohlcv.run, batch_size=bs_ohlcv, delay_between_batches_seconds=delay)
    print(f"[full_universe_run] F002 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")

    print(f"[full_universe_run] F005 (fundamentals) over {len(symbols)} symbols (batch_size={bs_fund}, delay={delay}s -- 4 calls/symbol)...")
    outcome = bo.run_batched(con, "F005", symbols, fundamentals.run, batch_size=bs_fund, delay_between_batches_seconds=delay)
    print(f"[full_universe_run] F005 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")

    print(f"[full_universe_run] F006 (corporate events) over {len(symbols)} symbols (batch_size={bs_ohlcv}, delay={delay}s)...")
    outcome = bo.run_batched(con, "F006", symbols, corporate_events.run, batch_size=bs_ohlcv, delay_between_batches_seconds=delay)
    print(f"[full_universe_run] F006 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")


def run_validation_and_join_stage_full_universe(symbols: list[str]) -> None:
    """Step 4: F101 then F102, against whatever's actually landed so far.
    Identical logic to staged_pilot_run.py's version -- F101 raising is a
    real stop, not caught."""
    print("[full_universe_run] F101 (cross-dataset validation)...")
    validate_crossref.validate_or_raise()
    print("[full_universe_run] F101 PASS")

    con = migrations.run_all_migrations()
    print(f"[full_universe_run] F102 (point-in-time join) over {len(symbols)} symbols...")
    total_events = 0
    for i, symbol in enumerate(symbols, start=1):
        n = pit_join.write_events(pit_join.build_events_for_symbol(con, symbol), con)
        total_events += n
        if i % 200 == 0:
            print(f"[full_universe_run]   F102 progress: {i}/{len(symbols)} symbols joined, {total_events} events so far")
    print(f"[full_universe_run] F102 done: {total_events} total events written across {len(symbols)} symbols")


def run_backtest_stage() -> dict[str, object]:
    """Identical to staged_pilot_run.py's run_backtest_stage() -- same
    schema-bootstrap fix, same honest reporting. Duplicated here (rather
    than imported) to keep this script runnable standalone without a
    hard dependency on staged_pilot_run.py's module-level layout."""
    migrations.run_all_migrations()

    print("[full_universe_run] F201 (real, non-dry-run backtest)...")
    report = bmr.run(report_path="out/meanreversion_report.json", dry_run=False)
    print("[full_universe_run] F201 report written to out/meanreversion_report.json")
    print(f"[full_universe_run] total_events_loaded={report['total_events_loaded']}")
    print(f"[full_universe_run] sentiment_class_counts={report['sentiment_class_counts']}")
    neg = report["overall"]["negative_sentiment_group"]
    print(f"[full_universe_run] negative_sentiment_group status={neg['status']} n={neg['n']}")
    if neg["status"] == "ok":
        print(f"[full_universe_run]   p_value={neg['p_value']} cohens_d={neg['cohens_d']}")
    else:
        print(
            "[full_universe_run]   NOT ENOUGH real negative-sentiment events yet "
            f"(n={neg['n']} < {report['min_sample_size']}) -- this is an honest "
            "result, not a failure."
        )
    return report


def load_full_universe(con) -> list[str]:  # type: ignore[no-untyped-def]
    """Every symbol in core.dim_symbol -- the full crawled universe (F001).
    If core.dim_symbol is empty (e.g. fresh/deleted DB), automatically runs
    dim_symbol.run() to populate the ~3,446 active symbols first."""
    rows = con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()
    if not rows:
        print("[full_universe_run] core.dim_symbol is empty -- running F001 (dim_symbol) to discover universe...")
        from crawlers import dim_symbol
        dim_symbol.run()
        rows = con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()
        print(f"[full_universe_run] F001 populated {len(rows)} symbols into core.dim_symbol")
    return [r[0] for r in rows]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Full-universe crawl (all of core.dim_symbol, not just the pilot subset) -> F101/F102 -> optional F201"
    )
    parser.add_argument(
        "--skip-news", action="store_true", help="don't crawl F003/F004 news (e.g. on a stock-data-only re-run)"
    )
    parser.add_argument(
        "--news-only", action="store_true", help="crawl F003/F004 news only, skip stock datasets"
    )
    parser.add_argument(
        "--stock-only", action="store_true", help="run stock datasets only, skip F101/F102 (e.g. to check progress first)"
    )
    parser.add_argument(
        "--fast",
        "--silver",
        action="store_true",
        dest="fast",
        help="speed up crawls for Sponsor/Silver tier accounts (300 req/min limit, ~1.5h total crawl time)",
    )
    parser.add_argument(
        "--run-backtest",
        action="store_true",
        help="after F101/F102, also run F201's real (non-dry-run) backtest and print an honest summary",
    )
    parser.add_argument(
        "--backtest-only",
        action="store_true",
        help="skip crawling and F101/F102 entirely -- just re-run F201's backtest against whatever "
        "core.pit_events data already exists",
    )
    args = parser.parse_args()

    if args.backtest_only:
        run_backtest_stage()
        raise SystemExit(0)

    con = migrations.run_all_migrations()
    symbol_list = load_full_universe(con)
    print(f"[full_universe_run] full universe: {len(symbol_list)} symbols (from core.dim_symbol)")

    if not args.news_only:
        run_stock_data_stage_full_universe(con, symbol_list, fast=args.fast)

    if not args.skip_news:
        run_news_stage_full_universe(con, symbol_list, fast=args.fast)

    if not args.stock_only and not args.news_only:
        run_validation_and_join_stage_full_universe(symbol_list)

        if args.run_backtest:
            run_backtest_stage()

    print("[full_universe_run] complete.")
    print("[full_universe_run] check progress any time with: SELECT dataset_name, status, COUNT(*) FROM meta.crawl_progress GROUP BY 1,2")