import sys
from pathlib import Path
import time
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(r"d:\VESTA\src")))

from pipeline.sector_news_matcher import match_sector_tier_a, match_sector_tier_b, load_symbol_sector_map

print("=================================================================")
print(">>> VESTA FULL DATABASE SCAN: NEWS & MACRO_POLICY SECTOR LINKAGE <<<")
print("=================================================================")
start_total = time.time()

# 1. Connect to databases
con_main = duckdb.connect(r"d:\VESTA\db\vesta.duckdb", read_only=True)
con_stg = duckdb.connect(r"d:\VESTA\db\staging_sync.duckdb")

sym_to_sector, valid_symbols = load_symbol_sector_map(con_stg)
print(f"Loaded {len(sym_to_sector)} symbol-to-sector mappings.")

# 2. Query ALL headlines from core.news
print("\n1. Fetching all headlines from core.news...")
t0 = time.time()
df_news = con_main.execute("SELECT source_url, headline, source, published_at FROM core.news WHERE headline IS NOT NULL").df()
print(f"   Loaded {len(df_news):,} news records in {time.time()-t0:.2f}s.")

# Scan core.news
print("   Scanning core.news with 2-Tier Sector Matcher...")
t_scan = time.time()
records_news_signals = []

for _, row in df_news.iterrows():
    url = str(row["source_url"])
    headline = str(row["headline"])
    pub = row["published_at"]
    
    # Tier A match
    matches_a = match_sector_tier_a(headline, url=url)
    for m in matches_a:
        m["source_table"] = "core.news"
        m["published_at"] = pub
        records_news_signals.append(m)
        
    # Tier B match
    matches_b = match_sector_tier_b(headline, sym_to_sector, valid_symbols, url=url)
    for m in matches_b:
        m["source_table"] = "core.news"
        m["published_at"] = pub
        records_news_signals.append(m)

print(f"   Scanned {len(df_news):,} news articles in {time.time()-t_scan:.2f}s.")
print(f"   Found {len(records_news_signals):,} sector news signals in core.news.")

# 3. Query ALL headlines from core.macro_policy
print("\n2. Fetching all headlines from core.macro_policy...")
t0 = time.time()
df_macro = con_main.execute("SELECT source_url, headline, source, published_at FROM core.macro_policy WHERE headline IS NOT NULL").df()
print(f"   Loaded {len(df_macro):,} macro_policy records in {time.time()-t0:.2f}s.")

# Scan core.macro_policy
print("   Scanning core.macro_policy with 2-Tier Sector Matcher...")
t_scan = time.time()
records_macro_signals = []

for _, row in df_macro.iterrows():
    url = str(row["source_url"])
    headline = str(row["headline"])
    pub = row["published_at"]
    
    # Tier A match
    matches_a = match_sector_tier_a(headline, url=url)
    for m in matches_a:
        m["source_table"] = "core.macro_policy"
        m["published_at"] = pub
        records_macro_signals.append(m)
        
    # Tier B match
    matches_b = match_sector_tier_b(headline, sym_to_sector, valid_symbols, url=url)
    for m in matches_b:
        m["source_table"] = "core.macro_policy"
        m["published_at"] = pub
        records_macro_signals.append(m)

print(f"   Scanned {len(df_macro):,} macro_policy articles in {time.time()-t_scan:.2f}s.")
print(f"   Found {len(records_macro_signals):,} sector news signals in core.macro_policy.")

# 4. Ingest into core.sector_news_signal in staging_sync.duckdb
all_signals = records_news_signals + records_macro_signals
df_signals = pd.DataFrame(all_signals)

if not df_signals.empty:
    print(f"\n3. Ingesting {len(df_signals):,} sector news signals into core.sector_news_signal...")
    # Deduplicate on (source_url, sector_id)
    df_signals = df_signals.drop_duplicates(subset=["source_url", "sector_id"])
    
    # Register and bulk insert
    con_stg.execute("DELETE FROM core.sector_news_signal")
    con_stg.register("df_sig_view", df_signals)
    con_stg.execute("""
        INSERT INTO core.sector_news_signal (
            source_url, sector_id, sector_name, matched_keyword, match_tier, market_anchor, fetched_at
        )
        SELECT 
            source_url, sector_id, sector_name, matched_keyword, match_tier, market_anchor, CURRENT_TIMESTAMP
        FROM df_sig_view
    """)
    con_stg.unregister("df_sig_view")
    
    total_stored = con_stg.execute("SELECT count(*) FROM core.sector_news_signal").fetchone()[0]
    print(f"   Successfully stored {total_stored:,} unique sector signals in database.")

# 5. Compute Detailed Analytics & Linkage Statistics
print("\n=================================================================")
print(">>> LINKAGE ANALYTICS & STATISTICAL DISTRIBUTION REPORT <<<")
print("=================================================================")
print(f"Total articles scanned: {len(df_news) + len(df_macro):,}")
print(f"Total valid sector signals captured: {len(df_signals):,}")
print(f"Overall sector linkage hit rate: {len(df_signals)/(len(df_news)+len(df_macro))*100:.3f}% (Fail-closed precision)")

print("\n--- Breakdown by Match Tier ---")
print(df_signals["match_tier"].value_counts().to_string())

print("\n--- Breakdown by Source Table ---")
print(df_signals["source_table"].value_counts().to_string())

print("\n--- Top 15 Sectors by News Volume ---")
print(df_signals["sector_name"].value_counts().head(15).to_string())

print("\n--- Top Market Context Anchors Triggered ---")
print(df_signals["market_anchor"].value_counts().head(10).to_string())

print(f"\n*** COMPLETE: Entire scan finished in {time.time()-start_total:.2f}s ***")

con_main.close()
con_stg.close()
