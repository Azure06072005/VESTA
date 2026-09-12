import duckdb
from datetime import datetime

print("=" * 80)
print("MERGING NEW STAGING DATA INTO MAIN VESTA.DUCKDB")
print("Time:", datetime.now().isoformat())
print("=" * 80)

con = duckdb.connect('d:/VESTA/db/vesta.duckdb')

# 1. Merge staging_tnck macro_policy
con.execute("ATTACH 'd:/VESTA/db/staging_tnck.duckdb' AS tnck (READ_ONLY)")
tnck_cols = [c[0] for c in con.execute("DESCRIBE tnck.core.macro_policy").fetchall()]
col_str = ", ".join(tnck_cols)

print("\n[1] Merging staging_tnck.core.macro_policy...")
insert_tnck_sql = f"""
    INSERT INTO core.macro_policy ({col_str})
    SELECT {col_str}
    FROM tnck.core.macro_policy s
    WHERE s.source_url IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM core.macro_policy m WHERE m.source_url = s.source_url)
"""
rows_tnck = con.execute(insert_tnck_sql).fetchall()
print("  Successfully merged rows from staging_tnck.")
con.execute("DETACH tnck")

# 2. Merge staging_sync macro_policy and news
con.execute("ATTACH 'd:/VESTA/db/staging_sync.duckdb' AS sync_db (READ_ONLY)")

print("\n[2] Merging staging_sync.core.macro_policy...")
insert_sync_macro = f"""
    INSERT INTO core.macro_policy ({col_str})
    SELECT {col_str}
    FROM sync_db.core.macro_policy s
    WHERE s.source_url IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM core.macro_policy m WHERE m.source_url = s.source_url)
"""
con.execute(insert_sync_macro)
print("  Successfully merged macro_policy from staging_sync.")

print("\n[3] Merging staging_sync.core.news...")
news_cols = [c[0] for c in con.execute("DESCRIBE core.news").fetchall()]
news_col_str = ", ".join(news_cols)

insert_sync_news = f"""
    INSERT INTO core.news ({news_col_str})
    SELECT {news_col_str}
    FROM sync_db.core.news s
    WHERE s.source_url IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM core.news m WHERE m.source_url = s.source_url)
"""
con.execute(insert_sync_news)
print("  Successfully merged news from staging_sync.")
con.execute("DETACH sync_db")

# Final verification
total_macro = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
total_news = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
print("\n" + "=" * 80)
print(f"MERGE COMPLETE:")
print(f"  core.macro_policy total rows: {total_macro:,}")
print(f"  core.news total rows:         {total_news:,}")
print("=" * 80)

con.close()
