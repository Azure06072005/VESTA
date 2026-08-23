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

import subprocess
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import migrations  # noqa: E402
from etl import batch_orchestrator as bo  # noqa: E402
from pipeline import validate_crossref  # noqa: E402
from pipeline import pit_join  # noqa: E402
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
            env={"PYTHONPATH": "src"},
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the staged pilot plan end-to-end")
    parser.add_argument("symbols_file", help="e.g. scratch/pilot_symbols.txt")
    parser.add_argument(
        "--skip-news", action="store_true", help="don't start F003/F004 background crawls (e.g. on a re-run)"
    )
    parser.add_argument(
        "--stock-only", action="store_true", help="run step 2 only, skip F101/F102 (e.g. to check progress first)"
    )
    args = parser.parse_args()

    symbol_list = load_symbols(args.symbols_file)
    print(f"[staged_pilot_run] pilot universe: {len(symbol_list)} symbols")

    if not args.skip_news:
        start_background_news_crawls(args.symbols_file)

    run_stock_data_stage(symbol_list)

    if not args.stock_only:
        run_validation_and_join_stage(symbol_list)

    print("[staged_pilot_run] complete. Background F003/F004 crawls (if started) continue independently --")
    print("[staged_pilot_run] check progress any time with: SELECT dataset_name, status, COUNT(*) FROM meta.crawl_progress GROUP BY 1,2")