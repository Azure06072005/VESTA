import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from etl import migrations
from etl import batch_orchestrator as bo
from crawlers import vnstock_news

def load_full_universe(con):
    rows = con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()
    return [r[0] for r in rows]

if __name__ == "__main__":
    con = migrations.run_all_migrations()
    symbols = load_full_universe(con)
    print(f"Running F003 for {len(symbols)} symbols...")
    outcome = bo.run_batched(con, "F003", symbols, vnstock_news.run, batch_size=300, delay_between_batches_seconds=0)
    print(f"F003 done: {len(outcome['succeeded'])} ok, {len(outcome['failed'])} failed, {len(outcome['empty'])} empty")
