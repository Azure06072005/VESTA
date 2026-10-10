"""
scratch/deduplicate_all_tables.py

Comprehensive Deduplication Engine across all 5 Mission Databases:
Eliminates duplicate rows caused by repeated crawler runs appending with different fetched_at.
Keeps the latest record (MAX fetched_at or MAX rowid) for each unique business key.
"""
import duckdb
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TABLE_KEYS = {
    "vesta_fundamentals.duckdb": [
        ("core", "fundamentals", ["symbol", "period_end"]),
        ("staging", "fundamentals", ["symbol", "period_end"]),
        ("core", "cafef_disclosures", ["symbol", "company_name", "exchange", "year"]),
        ("staging", "cafef_disclosures", ["symbol", "company_name", "exchange", "year"]),
        ("preprocessed", "fundamentals_ratios", ["symbol", "period_end"]),
    ],
    "vesta_news.duckdb": [
        ("core", "macro_policy", ["source", "issuing_body", "doc_type", "doc_number"]),
        ("staging", "macro_policy", ["source", "issuing_body", "doc_type", "doc_number"]),
        ("core", "news_resources", ["source", "issuing_body", "doc_type", "doc_number"]),
        ("staging", "news_resources", ["source", "issuing_body", "doc_type", "doc_number"]),
    ],
    "vesta_events.duckdb": [
        ("core", "corporate_events", ["symbol", "event_date", "event_type"]),
        ("staging", "corporate_events", ["symbol", "event_date", "event_type"]),
        ("preprocessed", "events", ["symbol", "event_date", "event_type"]),
    ],
    "vesta_market_index.duckdb": [
        ("core", "stock_research_reports", ["symbol", "broker", "title", "recommendation"]),
    ]
}

print("=" * 85)
print("KHỞI ĐỘNG CƠ CHẾ DEDUPLICATION & LÀM SẠCH BẢNG TRÙNG LẶP")
print("=" * 85)

total_purged = 0

for db_name, tables in TABLE_KEYS.items():
    db_path = Path("db") / db_name
    if not db_path.exists():
        continue

    print(f"\n📂 Xử lý: {db_name}")
    print("-" * 85)

    con = duckdb.connect(str(db_path), read_only=False)

    for schema, tname, keys in tables:
        full_table = f'"{schema}"."{tname}"'
        try:
            # Check table exists
            exists = con.execute(f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = '{schema}' AND table_name = '{tname}'
            """).fetchone()[0] > 0
            if not exists:
                continue

            # Check column existence
            col_info = con.execute(f"PRAGMA table_info({full_table});").fetchall()
            cols = [c[1] for c in col_info]
            valid_keys = [k for k in keys if k in cols]
            if not valid_keys:
                continue

            count_before = con.execute(f"SELECT COUNT(*) FROM {full_table}").fetchone()[0]
            if count_before == 0:
                continue

            order_col = "fetched_at" if "fetched_at" in cols else "rowid"
            partition_by = ", ".join([f'"{k}"' for k in valid_keys])

            # Create clean temp table keeping row_number() = 1
            con.execute(f"""
                CREATE OR REPLACE TEMPORARY TABLE _tmp_dedup AS
                SELECT * EXCLUDE (_rn) FROM (
                    SELECT *, ROW_NUMBER() OVER(PARTITION BY {partition_by} ORDER BY "{order_col}" DESC) as _rn
                    FROM {full_table}
                ) WHERE _rn = 1;
            """)

            count_after = con.execute("SELECT COUNT(*) FROM _tmp_dedup").fetchone()[0]
            purged = count_before - count_after

            if purged > 0:
                con.execute(f"DELETE FROM {full_table};")
                con.execute(f"INSERT INTO {full_table} SELECT * FROM _tmp_dedup;")
                print(f"  ✨ {schema}.{tname:28}: {count_before:10,d} -> {count_after:10,d} | Giảm {purged:8,d} dòng trùng (-{(purged/count_before*100):.1f}%)")
                total_purged += purged
            else:
                print(f"  ✅ {schema}.{tname:28}: {count_before:10,d} dòng | Không có trùng lặp")

            con.execute("DROP TABLE IF EXISTS _tmp_dedup;")

        except Exception as e:
            print(f"  ❌ Lỗi khi khử trùng {schema}.{tname}: {e}")

    try:
        con.execute("CHECKPOINT;")
    except Exception:
        pass
    con.close()

print("\n" + "=" * 85)
print(f"TỔNG KẾT: ĐÃ LOẠI BỎ THÀNH CÔNG {total_purged:,} BẢN GHI TRÙNG LẶP DO FETCHED_AT!")
print("=" * 85)
