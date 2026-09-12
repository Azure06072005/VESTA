import logging
from pathlib import Path
import sys
import duckdb
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("master_merge")

t0 = time.time()

# 1. Target database: vesta_consolidated.duckdb (working from vesta_merged_temp.duckdb)
temp_path = Path("d:/VESTA/db/vesta_merged_temp.duckdb")
staging_path = Path("d:/VESTA/db/crawlers_staging.duckdb")
backup_path = Path("d:/VESTA/db/vesta_latest_backup.duckdb")
consolidated_path = Path("d:/VESTA/db/vesta_consolidated.duckdb")

logger.info("Opening vesta_merged_temp.duckdb...")
con = duckdb.connect(str(temp_path), read_only=False)

# Check baseline count
base_count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
logger.info(f"Baseline rows in core.macro_policy: {base_count:,}")

# 2. Merge from crawlers_staging.duckdb
logger.info(f"Attaching {staging_path}...")
con.execute(f"ATTACH '{staging_path}' AS staging_db (READ_ONLY);")

staging_count = con.execute("SELECT count(*) FROM staging_db.core.macro_policy").fetchone()[0]
logger.info(f"Staging database contains {staging_count:,} articles.")

logger.info("Executing INSERT INTO core.macro_policy ON CONFLICT DO UPDATE...")
con.execute("""
    INSERT INTO core.macro_policy (
        source, issuing_body, doc_type, doc_number,
        published_at, available_at, headline, summary,
        body, source_url, fetched_at
    )
    SELECT
        source, issuing_body, doc_type, doc_number,
        published_at, available_at, headline, summary,
        body, source_url, fetched_at
    FROM staging_db.core.macro_policy
    ON CONFLICT (source_url) DO UPDATE SET
        headline = EXCLUDED.headline,
        summary = EXCLUDED.summary,
        body = EXCLUDED.body,
        doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
        fetched_at = EXCLUDED.fetched_at
""")

after_staging = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
logger.info(f"After staging merge: {after_staging:,} rows (+{after_staging - base_count:,} new unique articles!)")

con.execute("DETACH staging_db;")

# 3. Merge from vesta_latest_backup.duckdb
logger.info(f"Attaching {backup_path}...")
con.execute(f"ATTACH '{backup_path}' AS backup_db (READ_ONLY);")

backup_count = con.execute("SELECT count(*) FROM backup_db.core.macro_policy").fetchone()[0]
logger.info(f"Backup database contains {backup_count:,} articles.")

logger.info("Merging any missing articles from backup...")
con.execute("""
    INSERT INTO core.macro_policy (
        source, issuing_body, doc_type, doc_number,
        published_at, available_at, headline, summary,
        body, source_url, fetched_at
    )
    SELECT
        source, issuing_body, doc_type, doc_number,
        published_at, available_at, headline, summary,
        body, source_url, fetched_at
    FROM backup_db.core.macro_policy
    ON CONFLICT (source_url) DO NOTHING
""")

final_count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
logger.info(f"Final combined unique articles in core.macro_policy: {final_count:,} (+{final_count - after_staging:,} from backup)")

con.execute("DETACH backup_db;")

# Inspect breakdown by source
sources = con.execute("""
    SELECT source, count(*), min(published_at), max(published_at) 
    FROM core.macro_policy 
    GROUP BY source 
    ORDER BY count(*) DESC
""").fetchall()

con.close()

# Rename/copy to vesta_consolidated.duckdb
import shutil
shutil.copy(str(temp_path), str(consolidated_path))
logger.info(f"Saved consolidated database to {consolidated_path} ({consolidated_path.stat().st_size / (1024*1024):.2f} MB)")

dur = time.time() - t0
print("\n" + "=" * 80)
print(f"MASTER DATABASE CONSOLIDATION COMPLETE in {dur:.2f}s")
print("=" * 80)
print(f"Total Unique Macro Policy Articles: {final_count:,} articles")
print("-" * 80)
print(f"{'SOURCE':<25} | {'COUNT':<10} | {'DATE RANGE':<40}")
print("-" * 80)
for s, c, mn, mx in sources[:20]:
    print(f"{s:<25} | {c:<10,} | {str(mn)[:10]} -> {str(mx)[:10]}")
if len(sources) > 20:
    print(f"... and {len(sources)-20} more sources")
print("=" * 80)
