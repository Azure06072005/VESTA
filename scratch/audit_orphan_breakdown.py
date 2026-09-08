import json
import duckdb

con = duckdb.connect("d:/VESTA/db/vesta.duckdb", read_only=True)

dim_symbols = set(con.execute("SELECT symbol FROM core.dim_symbol").df()["symbol"])
cafef_symbols = set(con.execute("SELECT symbol FROM core.dim_symbol_cafef").df()["symbol"])
union_symbols = dim_symbols | cafef_symbols

raw_cafef = json.load(open("cafef_company_list.json", encoding="utf-8"))
all_cafef_directory = {x["Symbol"].strip().upper() for x in raw_cafef}
all_known_symbols = union_symbols | all_cafef_directory

tables = ["market_ohlcv_daily", "fundamentals", "corporate_events", "news", "realtime_quote_snapshot"]

print(f"Total symbols in core.dim_symbol: {len(dim_symbols)}")
print(f"Total symbols in core.dim_symbol_cafef: {len(cafef_symbols)}")
print(f"Total symbols in dim_symbol UNION dim_symbol_cafef: {len(union_symbols)}")
print(f"Total symbols in cafef_company_list.json (3,016 directory): {len(all_cafef_directory)}")
print()

print("=== 1. ORPHANS AGAINST core.dim_symbol ALONE (1,522 active listed equities) ===")
for t in tables:
    syms = set(con.execute(f"SELECT DISTINCT symbol FROM core.{t}").df()["symbol"])
    orphans = syms - dim_symbols
    print(f"  core.{t:25s}: total={len(syms):5d} | orphans={len(orphans):5d}")

print("\n=== 2. ORPHANS AGAINST core.dim_symbol UNION core.dim_symbol_cafef (2,506 symbols) ===")
for t in tables:
    syms = set(con.execute(f"SELECT DISTINCT symbol FROM core.{t}").df()["symbol"])
    orphans = syms - union_symbols
    print(f"  core.{t:25s}: total={len(syms):5d} | orphans={len(orphans):5d}")

print("\n=== 3. ORPHANS AGAINST ALL EQUITIES & DIRECTORY (dim_symbol + cafef_company_list.json) ===")
for t in tables:
    syms = set(con.execute(f"SELECT DISTINCT symbol FROM core.{t}").df()["symbol"])
    orphans = syms - all_known_symbols
    print(f"  core.{t:25s}: total={len(syms):5d} | non-directory orphans={len(orphans):5d}")

# Breakdown of non-directory orphans in market_ohlcv_daily
ohlcv_orphans = set(con.execute("SELECT DISTINCT symbol FROM core.market_ohlcv_daily").df()["symbol"]) - all_known_symbols
print(f"\nBreakdown of the {len(ohlcv_orphans)} market_ohlcv_daily symbols outside cafef_company_list.json:")
warrants = [s for s in ohlcv_orphans if s.startswith("C") and len(s) >= 8 and any(c.isdigit() for c in s)]
bonds = [s for s in ohlcv_orphans if any(c.isdigit() for c in s) and s not in warrants]
other = [s for s in ohlcv_orphans if s not in warrants and s not in bonds]
print(f"  - Expired Covered Warrants (e.g. CPNJ2103, CACB2201): {len(warrants)}")
print(f"  - Corporate / Govt Bonds (e.g. CII124021, CTG121031): {len(bonds)}")
print(f"  - Other / Historical ticker symbols (e.g. {other[:10]}): {len(other)}")
