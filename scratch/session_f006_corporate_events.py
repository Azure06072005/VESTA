import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from crawlers import corporate_events

def run():
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()
    
    # Get universe
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
    
    print(f"[{dt.datetime.now()}] Checking F006...")
    pending = bo.get_pending_symbols(con, "F006", symbols, max_retry=3)
    if not pending:
        print("  -> All symbols completed for F006.")
        return
        
    print(f"  -> {len(pending)} missing/pending symbols for F006. Crawling...")
    outcome = bo.run_batched(
        con=con,
        dataset_name="F006",
        symbols=pending,
        crawl_fn=corporate_events.run,
        batch_size=25,
        max_retry=3,
        delay_between_batches_seconds=2.0,
    )
    succeeded = len(outcome["succeeded"])
    failed = len(outcome["failed"])
    empty = len(outcome["empty"])
    print(f"  -> F006 finished: Succeeded: {succeeded}, Failed: {failed}, Empty: {empty}")

if __name__ == "__main__":
    run()
