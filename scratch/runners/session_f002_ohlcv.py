"""Session script for F002 (Market OHLCV Daily Crawler 2000-2026)."""
import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from crawlers import market_ohlcv

def run(batch_size: int = 40, delay: float = 2.0):
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
    print(f"[{dt.datetime.now()}] Starting F002 OHLCV crawl for {len(symbols)} symbols...")

    outcome = bo.run_batched(
        con=con,
        dataset_name="F002",
        symbols=symbols,
        crawl_fn=market_ohlcv.run,
        batch_size=batch_size,
        max_retry=3,
        delay_between_batches_seconds=delay,
    )
    print(f"[{dt.datetime.now()}] F002 crawl pass complete:")
    print(f"  -> Succeeded: {len(outcome['succeeded'])}, Failed: {len(outcome['failed'])}, Empty: {len(outcome['empty'])}")

    df = con.execute("SELECT dataset_name, status, count(*) AS n FROM meta.crawl_progress WHERE dataset_name='F002' GROUP BY dataset_name, status ORDER BY status;").df()
    print("\n--- F002 Progress Summary ---")
    print(df.to_string(index=False))

    ohlcv_count = con.execute("SELECT count(*), min(date), max(date) FROM core.market_ohlcv_daily").fetchone()
    print(f"Total OHLCV rows: {ohlcv_count[0]:,} (From {ohlcv_count[1]} to {ohlcv_count[2]})")

if __name__ == "__main__":
    run()
