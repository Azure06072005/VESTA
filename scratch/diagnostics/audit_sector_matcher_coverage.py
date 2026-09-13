"""scratch/diagnostics/audit_sector_matcher_coverage.py

Audits anchor gap and vocabulary gap across 1,139,301 articles in db/vesta.duckdb.
Measures empirical false negative candidates and outputs representative samples.
"""
import os
import re
import sys
import time
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.pipeline.sector_news_matcher import (
    match_sector_tier_a,
    SECTOR_TAXONOMY_DICT,
)

def run_audit():
    start_t = time.time()
    db_path = "db/vesta.duckdb"
    if not os.path.exists(db_path):
        db_path = "db/vesta_backup.duckdb"
        if not os.path.exists(db_path):
            print(f"Error: Neither vesta.duckdb nor vesta_backup.duckdb exists.")
            return

    print(f"Connecting to {db_path} (read-only)...")
    con = duckdb.connect(db_path, read_only=True)
    print("Loading 1,139,301 headlines from core.news and core.macro_policy...")
    t0 = time.time()
    df = con.execute("""
        SELECT source_url, headline, 'core.news' as source_table FROM core.news WHERE headline IS NOT NULL
        UNION ALL
        SELECT source_url, headline, 'core.macro_policy' as source_table FROM core.macro_policy WHERE headline IS NOT NULL
    """).df()
    con.close()
    load_t = time.time() - t0
    print(f"Loaded {len(df):,} rows in {load_t:.2f}s.")

    # Flatten keywords from SECTOR_TAXONOMY_DICT
    all_keywords = sorted(
        {kw for sec in SECTOR_TAXONOMY_DICT.values() for kw in sec["keywords"]},
        key=len,
        reverse=True
    )
    bare_kw_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(k) for k in all_keywords) + r")\b",
        re.IGNORECASE
    )

    print("Evaluating bare keyword presence...")
    headlines = df["headline"].fillna("").astype(str)
    t0 = time.time()
    df["has_bare_keyword"] = headlines.str.contains(bare_kw_pattern, regex=True)
    print(f"Evaluated bare keyword in {time.time()-t0:.2f}s.")
    print(f"Articles with bare sector keywords: {df['has_bare_keyword'].sum():,} ({df['has_bare_keyword'].mean()*100:.2f}%)")

    print("Evaluating match_sector_tier_a with updated anchor rules...")
    t0 = time.time()
    # Optimize: only run match_sector_tier_a if it has bare keyword or potential anchor
    matched_flags = []
    for h in headlines:
        if not h:
            matched_flags.append(False)
        else:
            matched_flags.append(len(match_sector_tier_a(h)) > 0)
    df["matched"] = matched_flags
    print(f"Evaluated match_sector_tier_a in {time.time()-t0:.2f}s.")

    matched_count = df["matched"].sum()
    print(f"Tier A matched: {matched_count:,} ({matched_count/len(df)*100:.3f}%)")

    # LOẠI 1 -- Anchor gap: có từ khóa ngành (đã khai báo đúng) nhưng KHÔNG match
    anchor_gap = df[df["has_bare_keyword"] & ~df["matched"]]
    print(f"\n[Anchor-gap candidates] {len(anchor_gap):,} bài có từ khóa ngành nhưng bị chặn vì thiếu neo thị trường / vướng admin filter.")
    
    os.makedirs("out", exist_ok=True)
    anchor_sample = anchor_gap.sample(min(100, len(anchor_gap)), random_state=42)
    anchor_sample[["source_table", "headline"]].to_csv("out/audit_anchor_gap_sample.csv", index=False, encoding="utf-8-sig")
    print("Saved 100 sample anchor-gap headlines to out/audit_anchor_gap_sample.csv")

    # LOẠI 2 -- Vocabulary gap sample
    no_match_no_kw = df[~df["matched"] & ~df["has_bare_keyword"]]
    vocab_sample = no_match_no_kw.sample(min(300, len(no_match_no_kw)), random_state=42)
    vocab_sample[["source_table", "headline"]].to_csv("out/audit_vocabulary_gap_sample_FOR_MANUAL_REVIEW.csv", index=False, encoding="utf-8-sig")
    print(f"Saved 300 sample non-matched headlines to out/audit_vocabulary_gap_sample_FOR_MANUAL_REVIEW.csv")

    total_t = time.time() - start_t
    print(f"\nCompleted full audit in {total_t:.2f}s.")

if __name__ == "__main__":
    run_audit()
