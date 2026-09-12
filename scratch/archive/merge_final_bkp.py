import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb')
con.execute("ATTACH 'd:/VESTA/db/vesta_latest_backup.duckdb' AS bkp (READ_ONLY)")

cols = [c[0] for c in con.execute('DESCRIBE core.macro_policy').fetchall()]
col_str = ', '.join(cols)

n_before = con.execute('SELECT count(*) FROM core.macro_policy').fetchone()[0]
con.execute(f"""
    INSERT INTO core.macro_policy ({col_str})
    SELECT {col_str}
    FROM bkp.core.macro_policy s
    WHERE s.source_url IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM core.macro_policy m WHERE m.source_url = s.source_url)
""")
n_after = con.execute('SELECT count(*) FROM core.macro_policy').fetchone()[0]
print(f"core.macro_policy: {n_before:,} -> {n_after:,} (+{n_after - n_before} rows merged)")
con.execute('DETACH bkp')
con.close()
