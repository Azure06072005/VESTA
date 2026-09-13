import re
import sys
from collections import Counter
import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DUCKDB_PATH = "d:/VESTA/db/vesta.duckdb"

print("=" * 80)
print("AUDITING STOCK TICKER MENTIONS IN CORE.MACRO_POLICY")
print("=" * 80)

con = duckdb.connect(DUCKDB_PATH, read_only=True)

# 1. Load active valid listed equity symbols from core.dim_symbol
valid_symbols = {r[0].strip().upper() for r in con.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall() if r[0]}
print(f"Loaded {len(valid_symbols):,} valid listed stock symbols from core.dim_symbol.")

# False positive blacklist / common Vietnamese acronyms that collide with 3-letter tickers
FALSE_POSITIVES = {
    "CEO", "BID", "SJC", "USD", "VND", "EUR", "CIA", "SME", "ABS", "VIP", "TST", 
    "CNN", "OTP", "VTV", "HTV", "IMF", "ADB", "FED", "CPI", "GDP", "FDI", "ODA", 
    "OPEC", "WTO", "APEC", "ASEAN", "EVN", "PVN", "TKV", "VEC", "VNR", "SBV", 
    "SSC", "MOF", "MPI", "MOIT", "MARD", "MOH", "MOT", "BCA", "BQP", "BXD", "BTN",
    "CAT", "FOX", "AMP", "AMD", "HDC", "ACB" # check ACB? Wait, ACB is a real bank! Only exclude true non-stock acronyms
}
# Keep ACB as valid stock! Only exclude non-stock acronyms:
FALSE_POSITIVES = {
    "CEO", "BID", "SJC", "USD", "VND", "EUR", "CIA", "SME", "ABS", "VIP", "TST", 
    "CNN", "OTP", "VTV", "HTV", "IMF", "ADB", "FED", "CPI", "GDP", "FDI", "ODA", 
    "OPEC", "WTO", "APEC", "ASEAN", "EVN", "PVN", "TKV", "VEC", "VNR", "SBV", 
    "SSC", "MOF", "MPI", "MOIT", "MARD", "MOH", "MOT", "BCA", "BQP", "BXD", "BTN"
}

# Regex patterns - Strict syntactic matching
STRICT_PATTERNS = [
    re.compile(r"\b(?:cổ\s+phiếu|cp)\s+([A-Z0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(?:mã\s+(?:chứng\s+khoán|ck)|mã:?)\s+([A-Z0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\((?:mã(?:\s+ck)?|ck):\s*([A-Z0-9]{3})\)", re.IGNORECASE),
    re.compile(r"\b(?:HOSE|HNX|UPCoM):\s*([A-Z0-9]{3})\b", re.IGNORECASE),
    re.compile(r"\b(?:CTCP|Tập đoàn|Tổng công ty|Công ty CP|Ngân hàng)\s+[A-ZÀ-Ỵa-zà-ỵ0-9\s\.\-]{2,30}\s*\(([A-Z0-9]{3})\)")
]

# Pattern B: Bare uppercase 3-letter word
BARE_TICKER_PATTERN = re.compile(r"\b([A-Z]{3})\b")

total_rows = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
print(f"Total rows in core.macro_policy to inspect: {total_rows:,}")

# Stream in chunks of 50,000 rows
CHUNK_SIZE = 50000
offset = 0

strict_headline_matches = 0
strict_body_matches = 0
strict_either_matches = 0

ticker_counter_strict = Counter()
ticker_counter_bare_headline = Counter()
source_ticker_count = Counter()
source_total_count = Counter()

print("\nScanning articles...")
while offset < total_rows:
    df_chunk = con.execute(f"""
        SELECT source, headline, body
        FROM core.macro_policy
        LIMIT {CHUNK_SIZE} OFFSET {offset}
    """).fetchdf()
    
    for _, row in df_chunk.iterrows():
        source = str(row['source'])
        headline = str(row['headline'] or '')
        body = str(row['body'] or '')
        source_total_count[source] += 1
        
        # 1. Check strict patterns in headline
        found_in_headline = set()
        for pat in STRICT_PATTERNS:
            for match in pat.findall(headline):
                m_upper = match.upper()
                if m_upper in valid_symbols and m_upper not in FALSE_POSITIVES:
                    found_in_headline.add(m_upper)
                    
        # 2. Check strict patterns in body (first 2000 chars for efficiency)
        found_in_body = set()
        body_sample = body[:2000]
        for pat in STRICT_PATTERNS:
            for match in pat.findall(body_sample):
                m_upper = match.upper()
                if m_upper in valid_symbols and m_upper not in FALSE_POSITIVES:
                    found_in_body.add(m_upper)
                    
        all_strict = found_in_headline | found_in_body
        if found_in_headline:
            strict_headline_matches += 1
        if found_in_body:
            strict_body_matches += 1
        if all_strict:
            strict_either_matches += 1
            source_ticker_count[source] += 1
            for sym in all_strict:
                ticker_counter_strict[sym] += 1

    offset += len(df_chunk)
    sys.stdout.write(f"\r  Processed: {offset:,} / {total_rows:,} ({offset/total_rows*100:.1f}%)")
    sys.stdout.flush()

print("\nScan completed!")

print("\n" + "=" * 80)
print("GENERAL STATISTICS OF TICKER MENTIONS IN CORE.MACRO_POLICY")
print("=" * 80)

pct_either = (strict_either_matches / total_rows) * 100
pct_hl = (strict_headline_matches / total_rows) * 100
pure_macro = total_rows - strict_either_matches
pct_pure = (pure_macro / total_rows) * 100

print(f"Total articles analyzed:                  {total_rows:,}")
print(f"Articles with strict ticker mentions:     {strict_either_matches:,} ({pct_either:.2f}%)")
print(f"  - Mentioned directly in Headline:       {strict_headline_matches:,} ({pct_hl:.2f}%)")
print(f"  - Mentioned in Lead Paragraph / Body:   {strict_body_matches:,} ({(strict_body_matches/total_rows)*100:.2f}%)")
print(f"Pure Macro/Policy articles (ZERO ticker): {pure_macro:,} ({pct_pure:.2f}%)")

print("\n--- BREAKDOWN BY NEWS SOURCE ---")
print(f"{'Source':<25} | {'Total Articles':<15} | {'With Ticker':<15} | {'% With Ticker':<15}")
print("-" * 75)
for src, total_c in source_total_count.most_common():
    with_c = source_ticker_count.get(src, 0)
    pct = (with_c / total_c) * 100 if total_c else 0
    print(f"{src:<25} | {total_c:<15,} | {with_c:<15,} | {pct:.2f}%")

print("\n--- TOP 30 MOST FREQUENTLY MENTIONED TICKERS ---")
for rank, (sym, count) in enumerate(ticker_counter_strict.most_common(30), 1):
    # get company name
    org = con.execute("SELECT organ_name FROM core.dim_symbol WHERE symbol = ?", [sym]).fetchone()
    org_name = org[0] if org else ""
    print(f"  #{rank:02d}. {sym:<5} ({org_name[:35]:<35}): {count:,} mentions")

con.close()
