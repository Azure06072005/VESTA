import duckdb

try:
    con = duckdb.connect("db/vesta_latest_backup.duckdb", read_only=True)
    res = con.execute("""
        SELECT source, COUNT(*), MIN(published_at), MAX(published_at)
        FROM core.macro_policy
        WHERE source IN ('tienphong', 'tuoitre', 'mof')
        GROUP BY source
    """).fetchall()
    print("=== Core Macro Policy Status ===")
    for r in res:
        print(f"Source: {r[0]} | Count: {r[1]} | Min Date: {r[2]} | Max Date: {r[3]}")
    
    total = con.execute("SELECT COUNT(*) FROM core.macro_policy").fetchone()[0]
    print(f"Total macro_policy records: {total}")
    con.close()
except Exception as e:
    print("DuckDB query error (likely write lock held):", e)
