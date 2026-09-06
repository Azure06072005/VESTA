import duckdb
import json
import os

def run_merge():
    con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=False)
    
    # 1. Merge from crawlers_staging.duckdb
    staging_path = 'd:/VESTA/db/crawlers_staging.duckdb'
    if os.path.exists(staging_path):
        try:
            con.execute(f"ATTACH '{staging_path}' AS staging_db (READ_ONLY);")
            con.execute("""
                INSERT INTO core.macro_policy
                SELECT * FROM staging_db.core.macro_policy
                ON CONFLICT (source_url) DO UPDATE SET
                    summary = excluded.summary,
                    body = COALESCE(excluded.body, core.macro_policy.body),
                    fetched_at = excluded.fetched_at
            """)
            con.execute("DETACH staging_db;")
            print("Successfully merged from crawlers_staging.duckdb")
        except Exception as e:
            print(f"Error merging staging db: {e}")
            try:
                con.execute("DETACH staging_db;")
            except Exception:
                pass

    # 2. Merge from json staging files
    for fname in ['staging_vietstock.json', 'staging_ssc.json', 'staging_vneconomy.json']:
        p = os.path.join('d:/VESTA/out', fname)
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    items = json.load(f)
                cnt = 0
                for item in items:
                    con.execute("""
                        INSERT INTO core.macro_policy (source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT (source_url) DO UPDATE SET
                            summary = excluded.summary,
                            body = COALESCE(excluded.body, core.macro_policy.body),
                            fetched_at = excluded.fetched_at
                    """, [
                        item.get('source'), item.get('issuing_body'), item.get('doc_type'), item.get('doc_number'),
                        item.get('published_at'), item.get('available_at'), item.get('headline'),
                        item.get('summary'), item.get('body'), item.get('source_url'), item.get('fetched_at')
                    ])
                    cnt += 1
                print(f"Merged {cnt} items from {fname}")
            except Exception as e:
                print(f"Error merging {fname}: {e}")

    total = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
    print(f"Total core.macro_policy after merge: {total:,}")
    
    # Sources breakdown
    res = con.execute("SELECT source, count(*) FROM core.macro_policy GROUP BY source ORDER BY count(*) DESC").fetchall()
    print("\n=== MACRO_POLICY SOURCES BREAKDOWN ===")
    for src, cnt in res:
        print(f"  {src}: {cnt:,}")
    
    con.close()

if __name__ == "__main__":
    run_merge()
