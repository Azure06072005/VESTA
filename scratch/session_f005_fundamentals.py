"""Session script for F005 (Fundamental crawler suite: Balance Sheet, Income Statement, Cash Flow, Ratio)."""
import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from crawlers import fundamentals

def run_crawler(batch_size: int = 25, delay: float = 2.0, period: str = "quarter"):
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
    pending = bo.get_pending_symbols(con, "F005", symbols, max_retry=3)

    print(f"=== F005 FUNDAMENTALS CRAWL SESSION ===")
    print(f"Total universe symbols: {len(symbols)}")
    print(f"Pending symbols to crawl: {len(pending)}")
    print(f"Starting F005 crawl at {dt.datetime.now()} (period={period})...\n")

    if not pending:
        print("All symbols already completed! No pending symbols.")
        report_status(con)
        return

    outcome = bo.run_batched(
        con=con,
        dataset_name="F005",
        symbols=pending,
        crawl_fn=lambda s: fundamentals.run(s, period=period),
        batch_size=batch_size,
        max_retry=3,
        delay_between_batches_seconds=delay,
    )
    print(f"\n[{dt.datetime.now()}] F005 crawl pass finished:")
    print(f"  -> Succeeded: {len(outcome['succeeded'])}, Failed: {len(outcome['failed'])}, Empty: {len(outcome['empty'])}")

    report_status(con)

def report_status(con=None):
    sys.stdout.reconfigure(encoding="utf-8")
    con = con or db.connect(read_only=True)
    print("\n=== F005 CURRENT STATUS & HISTORICAL DEPTH ===")
    summary_df = con.execute("""
        SELECT 
            report_type, 
            COUNT(*) as total_rows, 
            COUNT(DISTINCT symbol) as total_symbols,
            MIN(period_end) as earliest_period,
            MAX(period_end) as latest_period
        FROM core.fundamentals 
        GROUP BY report_type 
        ORDER BY report_type
    """).df()
    print(summary_df.to_string(index=False))

    progress_df = con.execute("""
        SELECT status, COUNT(*) as count 
        FROM meta.crawl_progress 
        WHERE dataset_name = 'F005'
        GROUP BY status 
        ORDER BY status
    """).df()
    print("\n--- meta.crawl_progress for F005 ---")
    print(progress_df.to_string(index=False))

if __name__ == "__main__":
    report_status()
