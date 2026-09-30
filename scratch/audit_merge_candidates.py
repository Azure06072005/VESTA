import duckdb
import json

db_c = "db/vesta.duckdb"
db_s = "db/vesta_snapshot.duckdb"

con = duckdb.connect(db_s, read_only=True)
con.execute(f"ATTACH '{db_c}' AS vesta (READ_ONLY)")

print("=== CHECKING TABLES FOR DUPLICATES AND MISSING ROWS ===\n")

table_keys = {
    "core.market_ohlcv_daily": ["symbol", "date"],
    "staging.market_ohlcv_daily": ["symbol", "date"],
    "core.market_ohlcv_1m": ["symbol", "time"],
    "core.market_foreign_flow_daily": ["symbol", "date"],
    "core.market_index_daily": ["index_code", "date"],
    "core.corporate_events": ["symbol", "event_date", "event_type"],
    "core.fundamentals": ["symbol", "report_type", "period_end"],
    "staging.fundamentals": ["symbol", "report_type", "period_end"],
    "core.news": ["source_url"],
    "staging.news": ["source_url"],
    "core.cafef_disclosures": ["symbol", "published_at", "title"],
    "core.stock_research_reports": ["report_id"],
    "meta.crawl_progress": ["dataset_name", "symbol"],
    "core.pit_events": ["symbol", "available_at", "event_type", "event_id"],
}

report = {}

for tbl, keys in table_keys.items():
    key_str = ", ".join(keys)
    print(f"Checking {tbl} (Keys: {key_str})...")
    
    # 1. Duplicates in snapshot
    try:
        dup_s = con.execute(f"""
            SELECT count(*) FROM (
                SELECT {key_str}, count(*) as cnt 
                FROM {tbl} 
                GROUP BY {key_str} 
                HAVING count(*) > 1
            )
        """).fetchone()[0]
    except Exception as e:
        dup_s = f"Err: {e}"

    # 2. Duplicates in vesta
    try:
        vesta_tbl = f"vesta.{tbl}"
        dup_v = con.execute(f"""
            SELECT count(*) FROM (
                SELECT {key_str}, count(*) as cnt 
                FROM {vesta_tbl} 
                GROUP BY {key_str} 
                HAVING count(*) > 1
            )
        """).fetchone()[0]
    except Exception as e:
        dup_v = f"Err: {e}"

    # 3. Missing in snapshot (Rows in vesta but not in snapshot)
    try:
        join_cond = " AND ".join([f"v.{k} = s.{k}" for k in keys])
        missing_in_snap = con.execute(f"""
            SELECT count(*) 
            FROM vesta.{tbl} v 
            LEFT JOIN {tbl} s ON {join_cond}
            WHERE s.{keys[0]} IS NULL
        """).fetchone()[0]
    except Exception as e:
        missing_in_snap = f"Err: {e}"

    # 4. Total rows in both
    try:
        rows_v = con.execute(f"SELECT count(*) FROM vesta.{tbl}").fetchone()[0]
        rows_s = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
    except Exception as e:
        rows_v, rows_s = -1, -1

    report[tbl] = {
        "keys": keys,
        "rows_vesta": rows_v,
        "rows_snapshot": rows_s,
        "duplicates_in_vesta": dup_v,
        "duplicates_in_snapshot": dup_s,
        "missing_in_snapshot_from_vesta": missing_in_snap,
    }
    print(f"  Rows Vesta: {rows_v:,} | Rows Snap: {rows_s:,}")
    print(f"  Dups in Vesta: {dup_v} | Dups in Snap: {dup_s}")
    msg = f"{missing_in_snap:,}" if isinstance(missing_in_snap, int) else missing_in_snap
    print(f"  Missing in Snap (can be merged from Vesta): {msg}\n")

con.close()

with open("scratch/merge_audit_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("Saved report to scratch/merge_audit_report.json")
