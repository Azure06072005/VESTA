import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / 'src'))
from etl import db, batch_orchestrator as bo
from crawlers import market_ohlcv

def main():
    con = db.bootstrap_schema()
    symbols = [r[0] for r in con.execute('SELECT symbol FROM core.dim_symbol ORDER BY symbol').fetchall()]
    print(f'Starting F002 crawl for {len(symbols)} symbols at {dt.datetime.now()}...')
    
    outcome = bo.run_batched(
        con=con,
        dataset_name='F002',
        symbols=symbols,
        crawl_fn=market_ohlcv.run,
        batch_size=40,
        max_retry=3,
        delay_between_batches_seconds=10.0
    )
    print(f'F002 crawl completed at {dt.datetime.now()}')
    print(f"Initial pass summary: {len(outcome['succeeded'])} succeeded, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")
    
    # Retry pass if any failed
    failed_symbols = [r[0] for r in con.execute("SELECT symbol FROM meta.crawl_progress WHERE dataset_name = 'F002' AND status = 'failed'").fetchall()]
    if failed_symbols:
        print(f"Retrying {len(failed_symbols)} failed symbols with conservative pacing...")
        retry_outcome = bo.run_batched(
            con=con,
            dataset_name="F002",
            symbols=failed_symbols,
            crawl_fn=market_ohlcv.run,
            batch_size=15,
            max_retry=3,
            delay_between_batches_seconds=5.0
        )
        print(f"Retry pass summary: {len(retry_outcome['succeeded'])} succeeded, {len(retry_outcome['failed'])} failed, {len(retry_outcome['empty'])} empty")

    print(f"F002 crawl fully completed at {dt.datetime.now()}")
    print("\n=== EVIDENCE QUERY ===")
    df = con.execute("SELECT dataset_name, status, count(*) AS n FROM meta.crawl_progress GROUP BY dataset_name, status ORDER BY dataset_name, status;").fetchdf()
    print(df)

if __name__ == '__main__':
    main()
