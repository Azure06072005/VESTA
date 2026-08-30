"""Comprehensive retry session for F002, F003, F005, F006, F007.
Uses the F008 retry coordinator via batch_orchestrator to clear the backlog.
"""
import sys
import pathlib
import datetime as dt
import time

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from crawlers import market_ohlcv, vnstock_news, fundamentals, corporate_events, snapshots
from etl.retry_failed_jobs import record_success, record_transient_failure, record_empty, EmptyResultError

def run():
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()

    print(f"[{dt.datetime.now()}] === Starting Comprehensive Retry Session ===")
    
    # Get universe
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]

    datasets = [
        ("F002", market_ohlcv.run),
        ("F003", vnstock_news.run),
        ("F005", lambda s: fundamentals.run(s, period="quarter")),
        ("F006", corporate_events.run),
    ]

    for dataset_name, crawl_fn in datasets:
        print(f"\n[{dt.datetime.now()}] Checking {dataset_name}...")
        pending = bo.get_pending_symbols(con, dataset_name, symbols, max_retry=3)
        if not pending:
            print(f"  -> All symbols completed for {dataset_name}.")
            continue
            
        print(f"  -> {len(pending)} missing/pending symbols for {dataset_name}. Retrying...")
        outcome = bo.run_batched(
            con=con,
            dataset_name=dataset_name,
            symbols=pending,
            crawl_fn=crawl_fn,
            batch_size=25,
            max_retry=3,
            delay_between_batches_seconds=2.0,
        )
        print(f"  -> {dataset_name} finished: Succeeded: {len(outcome['succeeded'])}, Failed: {len(outcome['failed'])}, Empty: {len(outcome['empty'])}")

    # F007 has special batching logic (50 symbols per API call)
    print(f"\n[{dt.datetime.now()}] Checking F007 (realtime_quote_snapshot)...")
    pending_f007 = bo.get_pending_symbols(con, "F007", symbols, max_retry=3)
    if not pending_f007:
        print("  -> All symbols completed for F007.")
    else:
        print(f"  -> {len(pending_f007)} missing/pending symbols for F007. Retrying in batches of 50...")
        batch_size = 50
        succeeded, failed, empty = 0, 0, 0
        for i in range(0, len(pending_f007), batch_size):
            batch = pending_f007[i : i + batch_size]
            try:
                n = snapshots.run(batch)
                for sym in batch:
                    record_success(con, "F007", sym)
                succeeded += len(batch)
            except EmptyResultError:
                for sym in batch:
                    record_empty(con, "F007", sym)
                empty += len(batch)
            except Exception as e:
                for sym in batch:
                    record_transient_failure(con, "F007", sym)
                failed += len(batch)
            time.sleep(1.5)
        print(f"  -> F007 finished: Succeeded: {succeeded}, Failed: {failed}, Empty: {empty}")

    print(f"\n[{dt.datetime.now()}] === Comprehensive Retry Session Complete ===")

if __name__ == "__main__":
    run()
