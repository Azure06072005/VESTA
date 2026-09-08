"""Staged pilot run -- implements the plan agreed 2026-08-22:
  1. (separate script) export_pilot_universe.py builds the symbol list
  2. F002/F005/F006 crawled synchronously, in that order (cheap, stable,
     needed before F102 can do anything)
  3. F003/F004 crawled in the BACKGROUND (own processes), since news
     depth only accumulates forward -- starting it late is unrecoverable
     lost time, so it must not wait for step 2 to finish
  4. F101 -> F102 run once step 2 completes, to validate the whole
     pipeline on real (if shallow) data before scaling to ~1800 symbols

This script only orchestrates -- it does not change any crawler or the
batch_orchestrator's retry/resume semantics. Safe to interrupt and re-run:
every step it calls is itself already resumable (F009 item 6).
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
from crawlers import market_ohlcv, fundamentals, corporate_events  # noqa: E402


def load_symbols(symbols_file: str) -> list[str]:
    with open(symbols_file, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def start_background_news_crawls(symbols_file: str) -> list[subprocess.Popen]:
    """Launches F003 and F004 as separate background processes over the
    pilot universe -- per the plan, these must NOT block on step 2, since
    every day of delay is unrecoverable lost news-depth accumulation.
    Returns the Popen handles so the caller can check on them later, but
    does not wait for them.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["PYTHONUTF8"] = "1"
    processes = []
    for dataset_name, module_name in [("F003", "crawlers.vnstock_news"), ("F004", "crawlers.cafef_news")]:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "etl.batch_orchestrator",
                dataset_name,
                module_name,
                symbols_file,
                "--batch-size",
                "20",
                "--delay",
                "15",
            ],
            cwd=repo_root,
            env=env,
        )
        print(f"[staged_pilot_run] started {dataset_name} in background, pid={proc.pid}")
        processes.append(proc)
    return processes


def run_stock_data_stage(symbols: list[str]) -> None:
    """Step 2: F002 -> F005 -> F006, synchronously, in that order --
    cheapest and most stable first, per the standing DECISIONS.md build-
    order preference.
    """
    con = migrations.run_all_migrations()  # bootstrap_schema() + all F009 migrations, not bootstrap alone

    print(f"[staged_pilot_run] F002 (OHLCV) over {len(symbols)} symbols...")
    outcome = bo.run_batched(con, "F002", symbols, market_ohlcv.run, batch_size=50, delay_between_batches_seconds=5)
    print(f"[staged_pilot_run] F002 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")

    print(f"[staged_pilot_run] F005 (fundamentals) over {len(symbols)} symbols...")
    outcome = bo.run_batched(con, "F005", symbols, fundamentals.run, batch_size=50, delay_between_batches_seconds=5)
    print(f"[staged_pilot_run] F005 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")

    print(f"[staged_pilot_run] F006 (corporate events) over {len(symbols)} symbols...")
    outcome = bo.run_batched(
        con, "F006", symbols, corporate_events.run, batch_size=50, delay_between_batches_seconds=5
    )
    print(f"[staged_pilot_run] F006 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")


def run_validation_and_join_stage(symbols: list[str]) -> None:
    """Step 4: F101 then F102, against whatever's actually landed so far.
    F101 raising is a real stop -- do not proceed to F102 on top of a
    known-broken cross-dataset state.
    """
    print("[staged_pilot_run] F101 (cross-dataset validation)...")
    validate_crossref.validate_or_raise()  # raises loudly if anything is wrong -- intentional, do not catch
    print("[staged_pilot_run] F101 PASS")

    con = migrations.run_all_migrations()  # bootstrap_schema() + all F009 migrations, not bootstrap alone
    print(f"[staged_pilot_run] F102 (point-in-time join) over {len(symbols)} symbols...")
    total_events = 0
    for symbol in symbols:
        n = pit_join.write_events(pit_join.build_events_for_symbol(con, symbol), con)
        total_events += n
    print(f"[staged_pilot_run] F102 done: {total_events} total events written across {len(symbols)} symbols")


def run_backtest_stage() -> dict[str, object]:
    """Step 5 (optional, --run-backtest): F201's real (non-dry-run)
    backtest against whatever real core.pit_events data now exists.

    This is deliberately a SEPARATE, opt-in stage rather than always-on
    at the end of the pilot run -- F102's own step already ran F101/F102
    against whatever news happened to be crawled *before* this run
    started; the background F003/F004 crawls launched by this same
    invocation will NOT have landed yet (news crawling takes real wall-
    clock time and this function returns immediately after step 2/4).
    Running F201 here reports on real, already-joined data -- it does
    NOT wait for the background crawls to finish, and the report's own
    n/insufficient_data status is what tells you honestly whether enough
    real news has accumulated yet. Re-run this stage alone later (once
    background crawls have had more time) with:
        python scratch/staged_pilot_run.py --backtest-only

    Calls migrations.run_all_migrations() first (schema bootstrap + all
    F009 migrations) so this also works standalone against a fresh/never-
    bootstrapped database -- backtest_meanreversion.run()'s own
    db.connect() does NOT bootstrap schema (only db.bootstrap_schema()
    does), so without this the first-ever --backtest-only invocation
    would fail with a raw CatalogException instead of a clean result.
    """
    migrations.run_all_migrations()  # ensure schema exists before bmr.run()'s db.connect()

    print("[staged_pilot_run] F201 (real, non-dry-run backtest)...")
    report = bmr.run(report_path="out/meanreversion_report.json", dry_run=False)
    print("[staged_pilot_run] F201 report written to out/meanreversion_report.json")
    print(f"[staged_pilot_run] total_events_loaded={report['total_events_loaded']}")
    print(f"[staged_pilot_run] sentiment_class_counts={report['sentiment_class_counts']}")
    neg = report["overall"]["negative_sentiment_group"]
    print(f"[staged_pilot_run] negative_sentiment_group status={neg['status']} n={neg['n']}")
    if neg["status"] == "ok":
        print(f"[staged_pilot_run]   p_value={neg['p_value']} cohens_d={neg['cohens_d']}")
    else:
        print(
            "[staged_pilot_run]   NOT ENOUGH real negative-sentiment events yet "
            f"(n={neg['n']} < {report['min_sample_size']}) -- this is an honest "
            "result, not a failure. Let background F003/F004 crawls run longer, "
            "then re-run with --backtest-only."
        )
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the staged pilot plan end-to-end")
    parser.add_argument(
        "symbols_file",
        nargs="?",
        default=None,
        help="e.g. scratch/pilot_symbols.txt (not required with --backtest-only)",
    )
    parser.add_argument(
        "--skip-news", action="store_true", help="don't start F003/F004 background crawls (e.g. on a re-run)"
    )
    parser.add_argument(
        "--stock-only", action="store_true", help="run step 2 only, skip F101/F102 (e.g. to check progress first)"
    )
    parser.add_argument(
        "--run-backtest",
        action="store_true",
        help="after F101/F102, also run F201's real (non-dry-run) backtest and print an honest "
        "n/p-value/effect-size summary -- reports insufficient_data plainly if there isn't enough "
        "real news yet, never fabricates a result",
    )
    parser.add_argument(
        "--backtest-only",
        action="store_true",
        help="skip crawling and F101/F102 entirely -- just re-run F201's backtest against "
        "whatever core.pit_events data already exists (e.g. after background news crawls "
        "have had more time to accumulate)",
    )
    args = parser.parse_args()

    if args.backtest_only:
        run_backtest_stage()
        raise SystemExit(0)

    if args.symbols_file is None:
        parser.error("symbols_file is required unless --backtest-only is given")

    symbol_list = load_symbols(args.symbols_file)
    print(f"[staged_pilot_run] pilot universe: {len(symbol_list)} symbols")

    if not args.skip_news:
        start_background_news_crawls(args.symbols_file)

    run_stock_data_stage(symbol_list)

    if not args.stock_only:
        run_validation_and_join_stage(symbol_list)

        if args.run_backtest:
            run_backtest_stage()

    print("[staged_pilot_run] complete. Background F003/F004 crawls (if started) continue independently --")
    print("[staged_pilot_run] check progress any time with: SELECT dataset_name, status, COUNT(*) FROM meta.crawl_progress GROUP BY 1,2")