import duckdb
import os

db_dir = 'd:/VESTA/db'
files = [f for f in os.listdir(db_dir) if f.endswith('.duckdb')]
main_db = os.path.join(db_dir, 'vesta.duckdb')

print("=" * 80)
print("AUDITING UNMERGED DATA ACROSS ALL DUCKDB FILES IN db/")
print("=" * 80)

con_main = duckdb.connect(main_db, read_only=True)

for f in sorted(files):
    if f == 'vesta.duckdb':
        continue
    fpath = os.path.join(db_dir, f).replace('\\', '/')
    fsize_mb = os.path.getsize(fpath) / (1024 * 1024)
    print(f"\n[{f}] ({fsize_mb:.2f} MB)")
    
    try:
        con_main.execute(f"ATTACH '{fpath}' AS cand (READ_ONLY)")
        
        # Get all tables in cand
        tables = con_main.execute("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_catalog = 'cand' AND table_schema IN ('core', 'staging', 'main')
            ORDER BY table_schema, table_name
        """).fetchall()
        
        if not tables:
            print("  No tables in core/staging/main.")
            
        for schema, t in tables:
            cnt = con_main.execute(f"SELECT count(*) FROM cand.{schema}.{t}").fetchone()[0]
            if cnt == 0:
                continue
                
            cols = [c[0] for c in con_main.execute(f"DESCRIBE cand.{schema}.{t}").fetchall()]
            
            # Check for unmerged data
            new_info = ""
            if t in ['news', 'macro_policy'] and 'source_url' in cols:
                try:
                    new_cnt = con_main.execute(f"""
                        SELECT count(*) FROM cand.{schema}.{t} s
                        WHERE s.source_url IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM core.{t} m WHERE m.source_url = s.source_url)
                    """).fetchone()[0]
                    new_info = f" -> {new_cnt:,} UNMERGED rows vs core.{t}"
                except Exception as e:
                    new_info = f" (err: {e})"
            elif t == 'market_ohlcv_daily':
                try:
                    new_cnt = con_main.execute(f"""
                        SELECT count(*) FROM cand.{schema}.{t} s
                        WHERE NOT EXISTS (SELECT 1 FROM core.{t} m WHERE m.symbol = s.symbol AND m.date = s.date)
                    """).fetchone()[0]
                    new_info = f" -> {new_cnt:,} UNMERGED rows vs core.{t}"
                except Exception as e:
                    new_info = f" (err: {e})"
            elif t == 'pit_events':
                try:
                    new_cnt = con_main.execute(f"""
                        SELECT count(*) FROM cand.{schema}.{t} s
                        WHERE NOT EXISTS (SELECT 1 FROM core.{t} m WHERE m.symbol = s.symbol AND m.published_at = s.published_at)
                    """).fetchone()[0]
                    new_info = f" -> {new_cnt:,} UNMERGED rows vs core.{t}"
                except Exception as e:
                    new_info = f" (err: {e})"
            
            print(f"  - {schema}.{t}: {cnt:,} rows{new_info}")
            
    except Exception as e:
        print(f"  Attach/Query error: {e}")
    finally:
        try:
            con_main.execute("DETACH cand")
        except Exception:
            pass

con_main.close()
print("\n" + "=" * 80)
print("AUDIT COMPLETED")
print("=" * 80)
