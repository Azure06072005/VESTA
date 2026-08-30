import sys
import pathlib
import datetime as dt
import time

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from etl.retry_failed_jobs import record_success, record_transient_failure, EmptyResultError
from crawlers import snapshots

def run():
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()
    
    # Get universe
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
    
    print(f"[{dt.datetime.now()}] Checking F007...")
    pending = bo.get_pending_symbols(con, "F007", symbols, max_retry=3)
    if not pending:
        print("  -> All symbols completed for F007.")
        return
        
    print(f"  -> {len(pending)} missing/pending symbols for F007. Crawling...")
    
    # We batch F007 by 50 symbols per API call because snapshots.run() supports lists,
    # which is much more efficient than 1-by-1 and avoids rate limits as much.
    batch_size = 50
    succeeded = 0
    failed = 0
    empty = 0
    
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        print(f"[{dt.datetime.now()}] F007: processing batch of {len(batch)} symbols...")
        try:
            # We call run() with the whole batch
            n = snapshots.run(batch)
            # If successful, we mark all symbols in this batch as successful
            for sym in batch:
                record_success(con, "F007", sym)
            succeeded += len(batch)
            print(f"  -> Batch success: wrote {n} rows")
        except EmptyResultError:
            for sym in batch:
                from etl.retry_failed_jobs import record_empty
                record_empty(con, "F007", sym)
            empty += len(batch)
        except Exception as e:
            print(f"  -> Batch failed: {e}")
            for sym in batch:
                record_transient_failure(con, "F007", sym)
            failed += len(batch)
            
        # small delay to respect rate limit (60 requests/min = 1 per sec)
        time.sleep(1.5)
        
    print(f"\n  -> F007 finished: Succeeded: {succeeded}, Failed: {failed}, Empty: {empty}")

if __name__ == "__main__":
    run()
