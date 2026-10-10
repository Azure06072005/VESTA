import duckdb
import os
import sys
import datetime as dt

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

dbs = {
    "ohlcv": "db/vesta_ohlcv.duckdb",
    "news": "db/vesta_news.duckdb",
    "fundamentals": "db/vesta_fundamentals.duckdb",
    "events": "db/vesta_events.duckdb",
    "market_index": "db/vesta_market_index.duckdb",
}

today = dt.date.today().isoformat()
print(f"=== AUDIT TOÀN DIỆN RANGE NGÀY CÁC BẢNG (HÔM NAY: {today}) ===")

date_col_candidates = [
    "date", "time", "published_at", "event_date", "ex_date", 
    "period_end", "period_date", "snapshot_date", "effective_date", 
    "start_date", "updated_at", "created_at", "fetched_at"
]

results = []

for db_name, db_path in dbs.items():
    if not os.path.exists(db_path):
        continue
    con = duckdb.connect(db_path, read_only=True)
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='core' AND table_type='BASE TABLE'").fetchall()]
    
    for tbl in tables:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info('core.{tbl}')").fetchall()]
        has_sym = "symbol" in cols or "ticker" in cols or "indicator" in cols or "index_code" in cols
        sym_col = "symbol" if "symbol" in cols else ("ticker" if "ticker" in cols else ("indicator" if "indicator" in cols else ("index_code" if "index_code" in cols else None)))
        
        found_date_col = None
        for dcol in date_col_candidates:
            if dcol in cols:
                found_date_col = dcol
                break
                
        cnt = con.execute(f"SELECT COUNT(*) FROM core.{tbl}").fetchone()[0]
        sym_cnt = con.execute(f"SELECT COUNT(DISTINCT {sym_col}) FROM core.{tbl}").fetchone()[0] if sym_col else None
        
        min_date, max_date = None, None
        if found_date_col:
            try:
                min_max = con.execute(f"""
                    SELECT 
                        CAST(MIN(CASE WHEN CAST({found_date_col} AS VARCHAR) >= '1990-01-01' THEN {found_date_col} ELSE NULL END) AS VARCHAR),
                        CAST(MAX(CASE WHEN CAST({found_date_col} AS VARCHAR) <= '{today}' THEN {found_date_col} ELSE NULL END) AS VARCHAR)
                    FROM core.{tbl}
                """).fetchone()
                min_date = str(min_max[0])[:10] if min_max and min_max[0] else None
                max_date = str(min_max[1])[:10] if min_max and min_max[1] else None
            except Exception as e:
                pass
                
        results.append({
            "db": db_name,
            "table": f"core.{tbl}",
            "records": cnt,
            "symbols": sym_cnt,
            "date_col": found_date_col,
            "min_date": min_date,
            "max_date": max_date,
        })
    con.close()

for r in results:
    dinfo = f"range: {r['min_date']} -> {r['max_date']} (col: {r['date_col']})" if r['date_col'] else "no date col"
    sinfo = f"{r['symbols']} syms" if r['symbols'] is not None else "no sym"
    print(f"[{r['db']:<12}] {r['table']:<35} | {r['records']:>10} rows | {sinfo:<10} | {dinfo}")
