import duckdb
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

dbs = [
    'db/vesta_snapshot.duckdb',
    'db/vesta_ohlcv.duckdb',
    'db/staging_sync.duckdb',
    'db/vesta_news.duckdb',
    'db/vesta_macro.duckdb'
]

targets = [
    'market_foreign_flow_daily',
    'corporate_events',
    'market_breadth_series',
    'sentiment_snapshot',
    'company_shareholders'
]

print("=== CHECKING LOCATIONS & SCHEMAS OF TARGET TABLES ===")
for db_path in dbs:
    if not os.path.exists(db_path):
        continue
    con = duckdb.connect(db_path, read_only=True)
    tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
    print(f"\nDB: {db_path}")
    for target in targets:
        # Check in default schema and core schema
        found = False
        try:
            # Check tables/views
            query = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{target}'"
            cols = con.execute(query).fetchall()
            if cols:
                count = con.execute(f"SELECT COUNT(*) FROM core.{target}").fetchone()[0]
                print(f"  FOUND core.{target} ({count:,} rows):")
                for col_name, dtype in cols[:10]:
                    print(f"    - {col_name}: {dtype}")
                if len(cols) > 10:
                    print(f"    ... and {len(cols)-10} more columns")
                found = True
        except Exception as e:
            pass
    con.close()
