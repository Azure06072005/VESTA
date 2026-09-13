"""test_pipeline/scripts/extract_text_preprocessing_samples.py

Extracts authentic sample records and comparisons for Step 5: Text Preprocessing & Disambiguation.
Outputs UTF-8 formatted markdown-compatible tables directly to stdout.
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from test_pipeline.f1xx_enrichment.test_text_preprocessing_and_disambiguation import (
    normalize_text,
    disambiguate_banking_entities,
    MinHashLSH,
    POLICY_PILLARS,
)

DB_PATH = "db/test_db/vesta_test.duckdb"
REPORT_JSON = "test_pipeline/out/text_preprocessing_report.json"


def extract_samples():
    con = duckdb.connect(DB_PATH, read_only=True)
    
    print("=" * 85)
    print("SAMPLE 1: RAW VS CLEANED TEXT (ADMINISTRATIVE BOILERPLATE STRIPPING)")
    print("=" * 85)
    df_raw = con.execute("""
        SELECT issuing_body, doc_type, headline, summary 
        FROM core.macro_policy 
        WHERE summary LIKE '%(Chinhphu.vn)%' OR summary LIKE '%(Thoibaonganhang.vn)%'
        LIMIT 2
    """).df()
    
    for idx, row in df_raw.iterrows():
        raw_full = f"{row['headline']}. {row['summary']}"
        clean_full = normalize_text(raw_full, is_policy=True)
        print(f"\n[Document {idx+1}] Source: {row['issuing_body']} | Doc Type: {row['doc_type']}")
        print(f"RAW TEXT   : {raw_full[:160]}...")
        print(f"CLEAN TEXT : {clean_full[:160]}...")
        
    print("\n" + "=" * 85)
    print("SAMPLE 2: EXACT & NEAR-DUPLICATE SYNDICATION PAIR (MINHASH JACCARD)")
    print("=" * 85)
    df_dups = con.execute("""
        SELECT headline, count(*) as cnt 
        FROM core.news 
        GROUP BY headline 
        HAVING count(*) >= 2 
        ORDER BY count(*) DESC 
        LIMIT 2
    """).df()
    
    for idx, row in df_dups.iterrows():
        print(f"\n[Duplicate Cluster {idx+1}] Count in DB: {row['cnt']} copies")
        print(f"Headline: {row['headline']}")
        
    print("\n" + "=" * 85)
    print("SAMPLE 3: SBV ENTITY DISAMBIGUATION (POLICY MAKER VS COMMERCIAL BANKING)")
    print("=" * 85)
    df_sbv = con.execute("""
        SELECT headline, summary 
        FROM core.macro_policy 
        WHERE headline LIKE '%Ngân hàng Nhà nước%' OR headline LIKE '%NHNN%'
        LIMIT 4
    """).df()
    
    sbv_rows = []
    for _, row in df_sbv.iterrows():
        h = row["headline"]
        s = row["summary"] or ""
        has_sbv, is_sec11 = disambiguate_banking_entities(h, s)
        sbv_rows.append({
            "Headline": h[:65] + "...",
            "Has SBV?": "YES",
            "Maps to Sector 11?": "YES" if is_sec11 else "NO (Filtered: Pure Policy Maker)",
            "Rationale": "Operational credit/lending" if is_sec11 else "Administrative / personnel only"
        })
    print(pd.DataFrame(sbv_rows).to_string(index=False))

    print("\n" + "=" * 85)
    print("SAMPLE 4: DETECTED MISROUTED CORPORATE FILINGS INSIDE MACRO_POLICY")
    print("=" * 85)
    df_misrouted = con.execute("""
        SELECT source, doc_type, headline, published_at
        FROM core.macro_policy 
        WHERE source = 'tinnhanhchungkhoan' AND (headline LIKE '%GDKHQ%' OR headline LIKE '%cổ tức%')
        LIMIT 3
    """).df()
    
    mis_rows = []
    for _, row in df_misrouted.iterrows():
        mis_rows.append({
            "Source": row["source"],
            "Current Table": "core.macro_policy",
            "Headline": row["headline"],
            "Target Destination": "core.news / core.corporate_events"
        })
    print(pd.DataFrame(mis_rows).to_string(index=False))
    
    con.close()


if __name__ == "__main__":
    extract_samples()
