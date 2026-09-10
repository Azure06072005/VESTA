import duckdb

con = duckdb.connect("d:/VESTA/db/vesta_latest_backup.duckdb")
dim_symbols = set(r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol").fetchall())
cafef_symbols = set(r[0] for r in con.execute("SELECT symbol FROM core.dim_symbol_cafef").fetchall())
union_symbols = dim_symbols | cafef_symbols

print(f"dim_symbol count: {len(dim_symbols)}")
print(f"dim_symbol_cafef count: {len(cafef_symbols)}")
print(f"Union (dim_symbol | dim_symbol_cafef) count: {len(union_symbols)}")

# Check fundamentals against dim_symbol vs union
fund_symbols = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.fundamentals").fetchall())
print(f"\nFundamentals total distinct symbols: {len(fund_symbols)}")
print(f"Fundamentals orphans vs dim_symbol alone: {len(fund_symbols - dim_symbols)}")
print(f"Fundamentals orphans vs union: {len(fund_symbols - union_symbols)}")

# Check market_ohlcv_daily against dim_symbol vs union
ohlcv_symbols = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.market_ohlcv_daily").fetchall())
ohlcv_orphans_alone = ohlcv_symbols - dim_symbols
ohlcv_orphans_union = ohlcv_symbols - union_symbols
print(f"\nOHLCV total distinct symbols: {len(ohlcv_symbols)}")
print(f"OHLCV orphans vs dim_symbol alone: {len(ohlcv_orphans_alone)}")
print(f"OHLCV orphans vs union: {len(ohlcv_orphans_union)}")
print(f"OHLCV resolved by cafef: {len(ohlcv_orphans_alone - ohlcv_orphans_union)}")

# Check news against dim_symbol vs union
news_symbols = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.news").fetchall())
news_orphans_alone = news_symbols - dim_symbols
news_orphans_union = news_symbols - union_symbols
print(f"\nNews total distinct symbols: {len(news_symbols)}")
print(f"News orphans vs dim_symbol alone: {len(news_orphans_alone)}")
print(f"News orphans vs union: {len(news_orphans_union)}")
print(f"News resolved by cafef: {len(news_orphans_alone - news_orphans_union)}")

# Check realtime_quote_snapshot against dim_symbol vs union
quote_symbols = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM core.realtime_quote_snapshot").fetchall())
quote_orphans_alone = quote_symbols - dim_symbols
quote_orphans_union = quote_symbols - union_symbols
print(f"\nQuote snapshot total distinct symbols: {len(quote_symbols)}")
print(f"Quote snapshot orphans vs dim_symbol alone: {len(quote_orphans_alone)}")
print(f"Quote snapshot orphans vs union: {len(quote_orphans_union)}")
print(f"Quote snapshot resolved by cafef: {len(quote_orphans_alone - quote_orphans_union)}")

# Let's inspect the remaining orphans in OHLCV and News
import re
cw_pattern = re.compile(r"^C[A-Z0-9]{7,9}$")
bond_pattern = re.compile(r"^[A-Z0-9]{3}[0-9]{6}$|^[0-9]{2}[A-Z0-9]+$")
etf_pattern = re.compile(r"^(?:FU|E1)[A-Z0-9]+")

def classify(syms):
    cws = [s for s in syms if s.startswith("C") and len(s) >= 8]
    etfs = [s for s in syms if s.startswith(("FU", "E1"))]
    bonds = [s for s in syms if any(char.isdigit() for char in s) and s not in cws and s not in etfs]
    equities = [s for s in syms if s not in cws and s not in etfs and s not in bonds]
    return cws, etfs, bonds, equities

cws, etfs, bonds, equities = classify(ohlcv_orphans_alone)
print(f"\nBreakdown of OHLCV orphans vs dim_symbol alone ({len(ohlcv_orphans_alone)} total):")
print(f"  Covered Warrants (CW): {len(cws)}")
print(f"  Bonds / Bond-like: {len(bonds)}")
print(f"  ETFs: {len(etfs)}")
print(f"  Equities (Delisted/Historical): {len(equities)}")
print(f"  Sample equities: {equities[:20]}")

# Let's check how many of those 172 equities are in cafef
eq_in_cafef = set(equities) & cafef_symbols
print(f"  Equities found in dim_symbol_cafef: {len(eq_in_cafef)}")
