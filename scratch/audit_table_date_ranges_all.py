"""
Audit max date and min date across all tables with date/time columns in all 5 databases.
Check which tables have reached istoday() (2026-10-09) and which need updates.
"""
import duckdb
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

dbs = [
    "vesta_ohlcv.duckdb",
    "vesta_market_index.duckdb",
    "vesta_fundamentals.duckdb",
    "vesta_events.duckdb",
    "vesta_news.duckdb",
]

print("=" * 85, flush=True)
print("AUDIT: MIN_DATE VÀ MAX_DATE TOÀN BỘ CÁC BẢNG (SO VỚI ISTODAY: 2026-10-09)", flush=True)
print("=" * 85, flush=True)

date_col_candidates = [
    "date", "time", "trade_date", "report_date", "period_date", "period_end",
    "published_at", "event_date", "ex_date", "snapshot_date", "start_date"
]

for db_name in dbs:
    db_path = Path("db") / db_name
    if not db_path.exists():
        continue
    con = duckdb.connect(str(db_path), read_only=True)
    tables = con.execute("""
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name;
    """).fetchall()

    print(f"\n📂 CSDL: {db_name}", flush=True)
    print("-" * 85, flush=True)

    for schema, tname in tables:
        full_table = f'"{schema}"."{tname}"'
        try:
            col_info = con.execute(f"PRAGMA table_info({full_table});").fetchall()
            cols = [c[1] for c in col_info]
            total_rows = con.execute(f"SELECT COUNT(*) FROM {full_table};").fetchone()[0]

            if total_rows == 0:
                print(f"  ⚪ {schema}.{tname:32}: 0 rows", flush=True)
                continue

            matched_date_cols = [c for c in cols if c.lower() in date_col_candidates]

            if not matched_date_cols:
                print(f"  ℹ️  {schema}.{tname:32}: {total_rows:10,d} rows | (Không có cột ngày)", flush=True)
                continue

            date_col = matched_date_cols[0]
            # Query min and max date
            res = con.execute(f"""
                SELECT 
                    MIN("{date_col}")::VARCHAR, 
                    MAX("{date_col}")::VARCHAR 
                FROM {full_table} 
                WHERE "{date_col}" IS NOT NULL;
            """).fetchone()

            min_d = str(res[0])[:10] if res and res[0] else "N/A"
            max_d = str(res[1])[:10] if res and res[1] else "N/A"

            is_today = (max_d == "2026-10-09")
            tag = "✅ T-0 (HÔM NAY)" if is_today else f"⚠️  {max_d}"

            print(f"  {schema}.{tname:32}: {total_rows:10,d} rows | Cột: {date_col:12} | Từ {min_d} đến {max_d} | {tag}", flush=True)

        except Exception as e:
            print(f"  ❌ {schema}.{tname:32}: Lỗi: {e}", flush=True)

    con.close()
