"""Session script for F001 (Reference Master: dim_symbol)."""
import sys
import pathlib
import datetime as dt

sys.path.insert(0, str(pathlib.Path.cwd() / "src"))
from etl import db
from crawlers import dim_symbol

def run():
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"[{dt.datetime.now()}] Running F001 dim_symbol crawl...")
    n = dim_symbol.run()
    print(f"[{dt.datetime.now()}] F001 dim_symbol done: {n} symbols written to core.dim_symbol")

    con = db.connect()
    count = con.execute("SELECT COUNT(*) FROM core.dim_symbol").fetchone()[0]
    print(f"Total symbols in core.dim_symbol: {count}")

if __name__ == "__main__":
    run()
