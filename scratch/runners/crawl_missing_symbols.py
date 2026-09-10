"""Crawl missing symbols for F001, F002, F003, F005."""
import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from crawlers import dim_symbol, market_ohlcv, vnstock_news, fundamentals

def run():
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()

    print(f"[{dt.datetime.now()}] === Starting missing symbols crawl ===")
    
    # F001: dim_symbol is a single-shot reference crawl, we just re-run it
    print(f"\n[{dt.datetime.now()}] Running F001 (dim_symbol) to ensure reference master is up to date...")
    n = dim_symbol.run()
    print(f"  -> F001 done: {n} symbols in core.dim_symbol")

    # Get universe
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]

    datasets = [
        ("F002", market_ohlcv.run),
        ("F003", vnstock_news.run),
        ("F005", lambda s: fundamentals.run(s, period="quarter")),
    ]

    for dataset_name, crawl_fn in datasets:
        print(f"\n[{dt.datetime.now()}] Checking {dataset_name}...")
        pending = bo.get_pending_symbols(con, dataset_name, symbols, max_retry=3)
        if not pending:
            print(f"  -> All symbols completed for {dataset_name}.")
            continue
            
        print(f"  -> {len(pending)} missing/pending symbols for {dataset_name}. Crawling...")
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

    print(f"\n[{dt.datetime.now()}] === Missing symbols crawl complete ===")

if __name__ == "__main__":
    run()
