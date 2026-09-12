import duckdb

con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=True)

for stg, name in [
    ('d:/VESTA/db/staging_tnck.duckdb', 'staging_tnck'),
    ('d:/VESTA/db/staging_sync.duckdb', 'staging_sync'),
    ('d:/VESTA/db/staging_tuoitre.duckdb', 'staging_tuoitre'),
    ('d:/VESTA/db/crawlers_staging.duckdb', 'crawlers_staging')
]:
    con.execute(f"ATTACH '{stg}' AS {name} (READ_ONLY)")
    try:
        new_macro = con.execute(f"""
            SELECT count(*) 
            FROM {name}.core.macro_policy s
            WHERE s.source_url IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM core.macro_policy m WHERE m.source_url = s.source_url)
        """).fetchone()[0]
        print(f"{name}: {new_macro:,} NEW macro_policy rows")
    except Exception as e:
        print(f"{name} macro error: {e}")
        
    try:
        new_news = con.execute(f"""
            SELECT count(*) 
            FROM {name}.core.news s
            WHERE s.source_url IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM core.news m WHERE m.source_url = s.source_url)
        """).fetchone()[0]
        if new_news > 0:
            print(f"{name}: {new_news:,} NEW news rows")
    except Exception:
        pass
    con.execute(f"DETACH {name}")
