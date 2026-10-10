import duckdb
from pathlib import Path

db_dir = Path('d:/VESTA/db')
for db_name in ['vesta_ohlcv.duckdb', 'vesta_market_index.duckdb', 'vesta_news.duckdb', 'vesta_fundamentals.duckdb', 'vesta_events.duckdb']:
    db_file = db_dir / db_name
    print(f"\n=== DATABASE: {db_file.name} ===")
    con = duckdb.connect(str(db_file), read_only=True)
    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')").fetchall()
    for sch, tbl in tables:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {sch}.\"{tbl}\"").fetchone()[0]
            cols = [c[1] for c in con.execute(f"PRAGMA table_info('{sch}.\"{tbl}\"')").fetchall()]
            max_d = None
            d_name = None
            for dcol in ['date', 'published_at', 'time', 'ex_date', 'effective_date', 'year_period']:
                if dcol in cols:
                    try:
                        max_d = con.execute(f"SELECT MAX({dcol}) FROM {sch}.\"{tbl}\"").fetchone()[0]
                        d_name = dcol
                        break
                    except Exception:
                        pass
            print(f"  [{sch}.{tbl}] {count:,} rows | max_{d_name}={max_d}")
        except Exception as e:
            print(f"  [{sch}.{tbl}] error: {e}")
    con.close()
