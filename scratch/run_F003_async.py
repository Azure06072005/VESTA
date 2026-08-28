import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from etl import migrations
from etl import async_batch_orchestrator as abo
from crawlers import vnstock_news

def load_full_universe(con):
    rows = con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()
    return [r[0] for r in rows]

if __name__ == "__main__":
    con = migrations.run_all_migrations()
    symbols = load_full_universe(con)

    print(f"Running F003 asynchronously for {len(symbols)} symbols...")
    
    # max_concurrency=4 with ~0.5s per request averages ~480 req/min
    # adding delay_between_requests_seconds=0.2s makes each worker take ~0.7s
    # 4 workers * (60 / 0.7) = ~340 req/min, which is close to the Sponsor limit (300).
    # We can use max_concurrency=3 with 0 delay to be safe (~360 req/min).
    outcome = abo.run_concurrently(
        con=con, 
        dataset_name="F003", 
        symbols=symbols, 
        crawl_fn=lambda sym, c: vnstock_news.run(sym, con=c), 
        max_concurrency=3, 
        delay_between_requests_seconds=0.1
    )
    print(f"F003 async done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")
