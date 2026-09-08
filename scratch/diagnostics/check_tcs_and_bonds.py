import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import json
import duckdb
import re

# 1. Check TCS in cafef_company_list.json
entries = json.load(open("cafef_company_list.json", encoding="utf-8"))
tcs_exact = [e for e in entries if e.get("Symbol", "").upper() == "TCS"]
print("TCS exact symbol matches in cafef_company_list.json:", tcs_exact)

coc_sau = [e for e in entries if "cọc sáu" in e.get("Title", "").lower() or "coc sau" in e.get("Title", "").lower()]
print("Title matching 'cọc sáu':", [(e["Symbol"], e["Title"]) for e in coc_sau])

tdn = [e for e in entries if e.get("Symbol", "").upper() == "TDN"]
print("TDN in cafef_company_list.json:", [(e["Symbol"], e["Title"]) for e in tdn])

# 2. Check all digit-starting symbols in DuckDB
con = duckdb.connect("d:/VESTA/db/vesta_latest_backup.duckdb", read_only=True)
tables = ["core.market_ohlcv_daily", "core.news", "core.realtime_quote_snapshot"]
all_digit_symbols = set()
for t in tables:
    syms = [r[0] for r in con.execute(f"SELECT DISTINCT symbol FROM {t} WHERE symbol GLOB '[0-9]*'").fetchall()]
    all_digit_symbols.update(syms)
    print(f"Digit-starting symbols in {t} ({len(syms)}):", sorted(syms))

print(f"\nUnion of all digit-starting symbols across all tables ({len(all_digit_symbols)}):", sorted(all_digit_symbols))

for s in sorted(all_digit_symbols):
    print(f"  {s}: len={len(s)}")

# 3. Check all symbols in market_ohlcv_daily containing '-' or 'INDEX' or 'ALL'
index_candidates = [r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.market_ohlcv_daily WHERE symbol LIKE '%-%' OR symbol LIKE '%INDEX%'").fetchall()]
print("\nIndex candidates with hyphen or INDEX:", index_candidates)
con.close()
