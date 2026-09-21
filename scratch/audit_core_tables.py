import duckdb
import json

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)
core_tables = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'core'").fetchall()

summary = {}
for (tbl,) in sorted(core_tables):
    try:
        cnt = con.execute(f"SELECT COUNT(*) FROM core.{tbl}").fetchone()[0]
        cols = [r[1] for r in con.execute(f"PRAGMA table_info('core.{tbl}')").fetchall()]
        sym_col = 'symbol' if 'symbol' in cols else ('ticker' if 'ticker' in cols else None)
        date_candidates = [c for c in cols if any(k in c.lower() for k in ['date', 'time', 'period_end', 'published_at', 'event_date', 'as_of_date'])]
        date_col = date_candidates[0] if date_candidates else None
        
        sym_cnt = con.execute(f"SELECT COUNT(DISTINCT {sym_col}) FROM core.{tbl}").fetchone()[0] if sym_col else None
        if date_col:
            min_d, max_d = con.execute(f"SELECT CAST(MIN({date_col}) AS VARCHAR), CAST(MAX({date_col}) AS VARCHAR) FROM core.{tbl}").fetchone()
        else:
            min_d, max_d = None, None
            
        summary[tbl] = {
            'rows': cnt,
            'symbols': sym_cnt,
            'date_col': date_col,
            'min_date': str(min_d)[:10] if min_d else None,
            'max_date': str(max_d)[:10] if max_d else None
        }
    except Exception as e:
        summary[tbl] = {'error': str(e)}

con.close()
print(json.dumps(summary, indent=2))
