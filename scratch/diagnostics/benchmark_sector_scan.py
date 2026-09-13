import sys
from pathlib import Path
import time
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(r"d:\VESTA\src")))

from pipeline.sector_news_matcher import match_sector_tier_a, match_sector_tier_b, load_symbol_sector_map

print("=== BENCHMARKING SECTOR MATCHER ON REAL DATA ===")
start = time.time()

# Connect read-only to main db
con_main = duckdb.connect(r"d:\VESTA\db\vesta.duckdb", read_only=True)
con_stg = duckdb.connect(r"d:\VESTA\db\staging_sync.duckdb", read_only=True)

sym_to_sector, valid_symbols = load_symbol_sector_map(con_stg)
print(f"Loaded {len(sym_to_sector)} symbol-to-sector mappings from staging DB.")

# Test 10,000 news articles
print("Testing 10,000 headlines from core.news...")
rows_news = con_main.execute("SELECT headline, source_url, source FROM core.news LIMIT 10000").fetchall()

t0 = time.time()
tier_a_matches = []
tier_b_matches = []

for headline, url, src in rows_news:
    if headline:
        res_a = match_sector_tier_a(headline, url=url)
        if res_a:
            tier_a_matches.extend(res_a)
        res_b = match_sector_tier_b(headline, sym_to_sector, valid_symbols, url=url)
        if res_b:
            tier_b_matches.extend(res_b)

elapsed = time.time() - t0
print(f"Processed 10,000 news headlines in {elapsed:.2f}s ({10000/elapsed:.0f} headlines/sec).")
print(f"Tier A matches (Sector Keyword with Market Anchor): {len(tier_a_matches)} ({len(tier_a_matches)/100:.2f}%)")
print(f"Tier B matches (Multi-symbol Co-occurrence): {len(tier_b_matches)} ({len(tier_b_matches)/100:.2f}%)")

# Test 10,000 macro_policy articles
print("\nTesting 10,000 headlines from core.macro_policy...")
rows_macro = con_main.execute("SELECT headline, source_url, source FROM core.macro_policy LIMIT 10000").fetchall()

t0 = time.time()
macro_a_matches = []
macro_b_matches = []

for headline, url, src in rows_macro:
    if headline:
        res_a = match_sector_tier_a(headline, url=url)
        if res_a:
            macro_a_matches.extend(res_a)
        res_b = match_sector_tier_b(headline, sym_to_sector, valid_symbols, url=url)
        if res_b:
            macro_b_matches.extend(res_b)

elapsed_m = time.time() - t0
print(f"Processed 10,000 macro headlines in {elapsed_m:.2f}s ({10000/elapsed_m:.0f} headlines/sec).")
print(f"Tier A matches in macro_policy: {len(macro_a_matches)} ({len(macro_a_matches)/100:.2f}%)")
print(f"Tier B matches in macro_policy: {len(macro_b_matches)} ({len(macro_b_matches)/100:.2f}%)")

# Show sample matches from core.news
if tier_a_matches:
    df_a = pd.DataFrame(tier_a_matches)
    print("\nTop matched sectors in core.news (Tier A):")
    print(df_a["sector_name"].value_counts().head(10).to_string())

if macro_a_matches:
    df_ma = pd.DataFrame(macro_a_matches)
    print("\nTop matched sectors in core.macro_policy (Tier A):")
    print(df_ma["sector_name"].value_counts().head(10).to_string())

con_main.close()
con_stg.close()
