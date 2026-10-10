"""
Optimized audit of fetched_at and duplicate rows across all 5 databases.
Uses flush=True and key-based duplicate detection.
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
print("AUDIT: PHÂN TÍCH TRÙNG LẶP DỮ LIỆU & TÁC ĐỘNG CỦA CỘT FETCHED_AT", flush=True)
print("=" * 85, flush=True)

findings = []

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

    print(f"\n📂 CSDL: {db_name} ({len(tables)} bảng)", flush=True)
    print("-" * 85, flush=True)

    for schema, tname in tables:
        full_table = f'"{schema}"."{tname}"'
        try:
            col_info = con.execute(f"PRAGMA table_info({full_table});").fetchall()
            cols = [c[1] for c in col_info]
            total_rows = con.execute(f"SELECT COUNT(*) FROM {full_table};").fetchone()[0]

            fetched_at_cols = [c for c in cols if 'fetched' in c.lower() or 'crawled' in c.lower() or 'ingested' in c.lower()]
            has_fetched_at = len(fetched_at_cols) > 0

            if total_rows == 0:
                print(f"  ⚪ {schema}.{tname:30}:          0 dòng (Bảng trống)", flush=True)
                continue

            # Determine business candidate keys
            candidate_keys = []
            if 'symbol' in cols and 'date' in cols:
                candidate_keys = ['symbol', 'date']
            elif 'symbol' in cols and 'time' in cols:
                candidate_keys = ['symbol', 'time']
            elif 'symbol' in cols and 'period_end' in cols:
                candidate_keys = ['symbol', 'period_end']
            elif 'index_code' in cols and 'date' in cols:
                candidate_keys = ['index_code', 'date']
            elif 'article_id' in cols:
                candidate_keys = ['article_id']
            elif 'url' in cols:
                candidate_keys = ['url']
            elif 'symbol' in cols and 'event_date' in cols:
                candidate_keys = ['symbol', 'event_date']
            elif 'symbol' in cols and 'ex_date' in cols:
                candidate_keys = ['symbol', 'ex_date']
            elif 'symbol' in cols and 'shareholder_name' in cols:
                candidate_keys = ['symbol', 'shareholder_name']
            else:
                # Use non-timestamp columns (up to 4 cols)
                non_ts = [c for c in cols if c not in fetched_at_cols and not c.endswith('_id')]
                candidate_keys = non_ts[:4] if non_ts else cols[:2]

            key_str = ", ".join([f'"{k}"' for k in candidate_keys])

            # Count distinct keys
            distinct_keys = con.execute(f"SELECT COUNT(DISTINCT ({key_str})) FROM {full_table}").fetchone()[0]
            dupes = total_rows - distinct_keys
            pct_dupe = (dupes / total_rows * 100.0) if total_rows > 0 else 0.0

            ts_tag = f"[CÓ {', '.join(fetched_at_cols)}]" if has_fetched_at else "[KHÔNG có fetched_at]"
            
            if dupes > 0:
                print(f"  ⚠️  {schema}.{tname:28}: {total_rows:10,d} dòng | {distinct_keys:10,d} unique ({key_str}) | {dupes:8,d} TRÙNG ({pct_dupe:5.1f}%) | {ts_tag}", flush=True)
                findings.append({
                    "db": db_name,
                    "table": f"{schema}.{tname}",
                    "total": total_rows,
                    "distinct": distinct_keys,
                    "dupes": dupes,
                    "pct": pct_dupe,
                    "keys": candidate_keys,
                    "fetched_at_cols": fetched_at_cols
                })
            else:
                print(f"  ✅ {schema}.{tname:28}: {total_rows:10,d} dòng | {distinct_keys:10,d} unique ({key_str}) | 0 trùng (SẠCH) | {ts_tag}", flush=True)

        except Exception as e:
            print(f"  ❌ {schema}.{tname:28}: Lỗi kiểm tra: {e}", flush=True)

    con.close()

print("\n" + "=" * 85, flush=True)
print(f"TỔNG KẾT: Có {len(findings)} bảng phát hiện bản ghi trùng lặp business key!", flush=True)
print("=" * 85, flush=True)
