"""Session script for F003 / F004 (Company News Crawlers: vnstock_news & CafeF)."""
import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db, batch_orchestrator as bo
from crawlers import vnstock_news, cafef_news

def run_vnstock_news(batch_size: int = 50, delay: float = 1.0):
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
    print(f"[{dt.datetime.now()}] Starting F003 vnstock_news crawl for {len(symbols)} symbols...")

    outcome = bo.run_batched(
        con=con,
        dataset_name="F003",
        symbols=symbols,
        crawl_fn=vnstock_news.run,
        batch_size=batch_size,
        max_retry=3,
        delay_between_batches_seconds=delay,
    )
    print(f"[{dt.datetime.now()}] F003 vnstock_news pass complete:")
    print(f"  -> Succeeded: {len(outcome['succeeded'])}, Failed: {len(outcome['failed'])}, Empty: {len(outcome['empty'])}")

    df = con.execute("SELECT dataset_name, status, count(*) AS n FROM meta.crawl_progress WHERE dataset_name='F003' GROUP BY dataset_name, status ORDER BY status;").df()
    print("\n--- F003 Progress Summary ---")
    print(df.to_string(index=False))

    news_count = con.execute("SELECT count(*), count(distinct symbol), min(published_at), max(published_at) FROM core.news WHERE source='vnstock'").fetchone()
    print(f"Total vnstock news: {news_count[0]:,} rows across {news_count[1]} symbols (From {news_count[2]} to {news_count[3]})")

def run_cafef_news(batch_size: int = 30, delay: float = 3.0):
    sys.stdout.reconfigure(encoding="utf-8")
    con = db.bootstrap_schema()
    symbols = [r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol ORDER BY symbol").fetchall()]
    print(f"[{dt.datetime.now()}] Starting F004 CafeF news crawl for {len(symbols)} symbols...")

    outcome = bo.run_batched(
        con=con,
        dataset_name="F004",
        symbols=symbols,
        crawl_fn=cafef_news.run,
        batch_size=batch_size,
        max_retry=3,
        delay_between_batches_seconds=delay,
    )
    print(f"[{dt.datetime.now()}] F004 cafef_news pass complete:")
    print(f"  -> Succeeded: {len(outcome['succeeded'])}, Failed: {len(outcome['failed'])}, Empty: {len(outcome['empty'])}")

if __name__ == "__main__":
    run_vnstock_news()
