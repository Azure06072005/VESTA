import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from crawlers import cafef_news

def run():
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()
    
    # Get universe
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
    
    print(f"[{dt.datetime.now()}] Checking F004 (cafef.vn news)...")
    pending = bo.get_pending_symbols(con, "F004", symbols, max_retry=3)
    if not pending:
        print("  -> All symbols completed for F004.")
        return
        
    print(f"  -> {len(pending)} missing/pending symbols for F004. Crawling...")
    
    # For F004, the crawler itself (fetch_raw) explicitly enforces a REQUEST_DELAY_SECONDS = 2.0 
    # to avoid hammering the web server. We'll use batch_orchestrator to iterate with chunks of 25.
    outcome = bo.run_batched(
        con=con,
        dataset_name="F004",
        symbols=pending,
        crawl_fn=cafef_news.run,
        batch_size=25,
        max_retry=3,
        delay_between_batches_seconds=5.0, # extra safety delay between batches of scrapes
    )
    
    succeeded = len(outcome["succeeded"])
    failed = len(outcome["failed"])
    empty = len(outcome["empty"])
    print(f"  -> F004 finished: Succeeded: {succeeded}, Failed: {failed}, Empty: {empty}")

if __name__ == "__main__":
    run()
