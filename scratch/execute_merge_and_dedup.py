import duckdb
import time
import json
import os

db_canonical = "db/vesta.duckdb"
db_snapshot = "db/vesta_snapshot.duckdb"

print("="*60)
print("STARTING DATABASE COMBINE & DEDUPLICATION WORKFLOW")
print(f"Target DB (Master): {db_snapshot}")
print(f"Source DB (Archive): {db_canonical}")
print("="*60)

con = duckdb.connect(db_snapshot, read_only=False)
con.execute(f"ATTACH '{db_canonical}' AS vesta (READ_ONLY)")

t0 = time.time()
merge_log = []

try:
    con.execute("BEGIN TRANSACTION")
    print("\n[TRANSACTION STARTED]")

    # 1. meta.prediction_feedback_log (Create table & Insert)
    print("\n--- 1. Merging meta.prediction_feedback_log ---")
    con.execute("""
        CREATE TABLE IF NOT EXISTS meta.prediction_feedback_log AS 
        SELECT * FROM vesta.meta.prediction_feedback_log
    """)
    cnt_pred = con.execute("SELECT count(*) FROM meta.prediction_feedback_log").fetchone()[0]
    dup_pred = con.execute("SELECT count(*) FROM (SELECT prediction_id, count(*) FROM meta.prediction_feedback_log GROUP BY prediction_id HAVING count(*) > 1)").fetchone()[0]
    print(f"  Rows: {cnt_pred:,} | Duplicates: {dup_pred}")
    assert dup_pred == 0, "Duplicate found in prediction_feedback_log!"
    merge_log.append({"table": "meta.prediction_feedback_log", "inserted": cnt_pred, "total": cnt_pred, "duplicates": dup_pred})

    # 2. meta.model_drift_telemetry (Create schema if not exists)
    print("\n--- 2. Ensuring meta.model_drift_telemetry ---")
    con.execute("""
        CREATE TABLE IF NOT EXISTS meta.model_drift_telemetry AS 
        SELECT * FROM vesta.meta.model_drift_telemetry WHERE 1=0
    """)
    print("  Schema created successfully.")

    # 3. staging.news_resources (Create schema if not exists)
    print("\n--- 3. Ensuring staging.news_resources ---")
    con.execute("""
        CREATE TABLE IF NOT EXISTS staging.news_resources AS 
        SELECT * FROM vesta.staging.news_resources WHERE 1=0
    """)
    print("  Schema created successfully.")

    # 4. core.market_ohlcv_daily
    print("\n--- 4. Merging core.market_ohlcv_daily ---")
    before_ohlcv = con.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
    con.execute("""
        INSERT INTO core.market_ohlcv_daily
        SELECT * FROM vesta.core.market_ohlcv_daily v
        WHERE NOT EXISTS (
            SELECT 1 FROM core.market_ohlcv_daily s 
            WHERE s.symbol = v.symbol AND s.date = v.date
        )
    """)
    after_ohlcv = con.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
    inserted_ohlcv = after_ohlcv - before_ohlcv
    dup_ohlcv = con.execute("""
        SELECT count(*) FROM (
            SELECT symbol, date, count(*) 
            FROM core.market_ohlcv_daily 
            GROUP BY symbol, date 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  Before: {before_ohlcv:,} | Inserted: {inserted_ohlcv:,} | After: {after_ohlcv:,} | Duplicates: {dup_ohlcv}")
    assert dup_ohlcv == 0, "Duplicates found in core.market_ohlcv_daily!"
    merge_log.append({"table": "core.market_ohlcv_daily", "before": before_ohlcv, "inserted": inserted_ohlcv, "after": after_ohlcv, "duplicates": dup_ohlcv})

    # 5. staging.market_ohlcv_daily
    print("\n--- 5. Merging staging.market_ohlcv_daily ---")
    before_stg_ohlcv = con.execute("SELECT count(*) FROM staging.market_ohlcv_daily").fetchone()[0]
    con.execute("""
        INSERT INTO staging.market_ohlcv_daily
        SELECT * FROM vesta.staging.market_ohlcv_daily v
        WHERE NOT EXISTS (
            SELECT 1 FROM staging.market_ohlcv_daily s 
            WHERE s.symbol = v.symbol AND s.date = v.date
        )
    """)
    after_stg_ohlcv = con.execute("SELECT count(*) FROM staging.market_ohlcv_daily").fetchone()[0]
    inserted_stg_ohlcv = after_stg_ohlcv - before_stg_ohlcv
    dup_stg_ohlcv = con.execute("""
        SELECT count(*) FROM (
            SELECT symbol, date, count(*) 
            FROM staging.market_ohlcv_daily 
            GROUP BY symbol, date 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  Before: {before_stg_ohlcv:,} | Inserted: {inserted_stg_ohlcv:,} | After: {after_stg_ohlcv:,} | Duplicates: {dup_stg_ohlcv}")
    assert dup_stg_ohlcv == 0, "Duplicates found in staging.market_ohlcv_daily!"
    merge_log.append({"table": "staging.market_ohlcv_daily", "before": before_stg_ohlcv, "inserted": inserted_stg_ohlcv, "after": after_stg_ohlcv, "duplicates": dup_stg_ohlcv})

    # 6. core.market_ohlcv_1m
    print("\n--- 6. Merging core.market_ohlcv_1m ---")
    before_1m = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    con.execute("""
        INSERT INTO core.market_ohlcv_1m
        SELECT * FROM vesta.core.market_ohlcv_1m v
        WHERE NOT EXISTS (
            SELECT 1 FROM core.market_ohlcv_1m s 
            WHERE s.symbol = v.symbol AND s.time = v.time
        )
    """)
    after_1m = con.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
    inserted_1m = after_1m - before_1m
    dup_1m = con.execute("""
        SELECT count(*) FROM (
            SELECT symbol, time, count(*) 
            FROM core.market_ohlcv_1m 
            GROUP BY symbol, time 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  Before: {before_1m:,} | Inserted: {inserted_1m:,} | After: {after_1m:,} | Duplicates: {dup_1m}")
    assert dup_1m == 0, "Duplicates found in core.market_ohlcv_1m!"
    merge_log.append({"table": "core.market_ohlcv_1m", "before": before_1m, "inserted": inserted_1m, "after": after_1m, "duplicates": dup_1m})

    # 7. core.news
    print("\n--- 7. Merging core.news ---")
    before_news = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
    con.execute("""
        INSERT INTO core.news
        SELECT * FROM vesta.core.news v
        WHERE NOT EXISTS (
            SELECT 1 FROM core.news s 
            WHERE s.source_url = v.source_url
        )
    """)
    after_news = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
    inserted_news = after_news - before_news
    dup_news = con.execute("""
        SELECT count(*) FROM (
            SELECT source_url, count(*) 
            FROM core.news 
            WHERE source_url IS NOT NULL 
            GROUP BY source_url 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  Before: {before_news:,} | Inserted: {inserted_news:,} | After: {after_news:,} | Duplicates: {dup_news}")
    assert dup_news == 0, "Duplicates found in core.news!"
    merge_log.append({"table": "core.news", "before": before_news, "inserted": inserted_news, "after": after_news, "duplicates": dup_news})

    # 8. staging.news
    print("\n--- 8. Merging staging.news ---")
    before_stg_news = con.execute("SELECT count(*) FROM staging.news").fetchone()[0]
    con.execute("""
        INSERT INTO staging.news
        SELECT * FROM vesta.staging.news v
        WHERE NOT EXISTS (
            SELECT 1 FROM staging.news s 
            WHERE s.source_url = v.source_url
        )
    """)
    after_stg_news = con.execute("SELECT count(*) FROM staging.news").fetchone()[0]
    inserted_stg_news = after_stg_news - before_stg_news
    dup_stg_news = con.execute("""
        SELECT count(*) FROM (
            SELECT source_url, count(*) 
            FROM staging.news 
            WHERE source_url IS NOT NULL 
            GROUP BY source_url 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  Before: {before_stg_news:,} | Inserted: {inserted_stg_news:,} | After: {after_stg_news:,} | Duplicates: {dup_stg_news}")
    assert dup_stg_news == 0, "Duplicates found in staging.news!"
    merge_log.append({"table": "staging.news", "before": before_stg_news, "inserted": inserted_stg_news, "after": after_stg_news, "duplicates": dup_stg_news})

    # 9. core.macro_policy
    print("\n--- 9. Merging core.macro_policy ---")
    before_macro = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    con.execute("""
        INSERT INTO core.macro_policy
        SELECT * FROM vesta.core.macro_policy v
        WHERE NOT EXISTS (
            SELECT 1 FROM core.macro_policy s 
            WHERE s.source_url = v.source_url
        )
    """)
    after_macro = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    inserted_macro = after_macro - before_macro
    dup_macro = con.execute("""
        SELECT count(*) FROM (
            SELECT source_url, count(*) 
            FROM core.macro_policy 
            WHERE source_url IS NOT NULL 
            GROUP BY source_url 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  Before: {before_macro:,} | Inserted: {inserted_macro:,} | After: {after_macro:,} | Duplicates: {dup_macro}")
    assert dup_macro == 0, "Duplicates found in core.macro_policy!"
    merge_log.append({"table": "core.macro_policy", "before": before_macro, "inserted": inserted_macro, "after": after_macro, "duplicates": dup_macro})

    # 10. meta.crawl_progress
    print("\n--- 10. Merging meta.crawl_progress ---")
    before_prog = con.execute("SELECT count(*) FROM meta.crawl_progress").fetchone()[0]
    con.execute("""
        INSERT INTO meta.crawl_progress
        SELECT * FROM vesta.meta.crawl_progress v
        WHERE NOT EXISTS (
            SELECT 1 FROM meta.crawl_progress s 
            WHERE s.dataset_name = v.dataset_name AND s.symbol = v.symbol
        )
    """)
    after_prog = con.execute("SELECT count(*) FROM meta.crawl_progress").fetchone()[0]
    inserted_prog = after_prog - before_prog
    dup_prog = con.execute("""
        SELECT count(*) FROM (
            SELECT dataset_name, symbol, count(*) 
            FROM meta.crawl_progress 
            GROUP BY dataset_name, symbol 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  Before: {before_prog:,} | Inserted: {inserted_prog:,} | After: {after_prog:,} | Duplicates: {dup_prog}")
    assert dup_prog == 0, "Duplicates found in meta.crawl_progress!"
    merge_log.append({"table": "meta.crawl_progress", "before": before_prog, "inserted": inserted_prog, "after": after_prog, "duplicates": dup_prog})

    # Commit Transaction
    con.execute("COMMIT")
    print("\n[TRANSACTION COMMITTED SUCCESSFULLY]")

except Exception as e:
    con.execute("ROLLBACK")
    print(f"\n[ERROR - TRANSACTION ROLLED BACK]: {e}")
    con.close()
    exit(1)

# Check total rows and table counts after merge
total_tables = con.execute("SELECT count(*) FROM duckdb_tables() WHERE schema_name IN ('core', 'staging', 'meta', 'preprocessed')").fetchone()[0]
total_rows = 0
tables = con.execute("SELECT schema_name, table_name FROM duckdb_tables() WHERE schema_name IN ('core', 'staging', 'meta', 'preprocessed')").fetchall()
for s, t in tables:
    try:
        cnt = con.execute(f"SELECT count(*) FROM {s}.{t}").fetchone()[0]
        total_rows += cnt
    except:
        pass

con.close()

elapsed = time.time() - t0
size_after = os.path.getsize(db_snapshot)

summary = {
    "status": "SUCCESS",
    "elapsed_seconds": round(elapsed, 2),
    "db_path": db_snapshot,
    "size_bytes": size_after,
    "size_gb": round(size_after / (1024**3), 2),
    "total_tables": total_tables,
    "total_rows": total_rows,
    "merge_log": merge_log
}

with open("scratch/merge_execution_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print("\n" + "="*60)
print(f"MERGE & DEDUPLICATION COMPLETE in {elapsed:.2f}s")
print(f"Final Total Tables: {total_tables}")
print(f"Final Total Rows:   {total_rows:,}")
print(f"Final DB Size:      {size_after / (1024**3):.2f} GB")
print("Summary saved to scratch/merge_execution_summary.json")
print("="*60)
