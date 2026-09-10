import duckdb
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, 'd:/VESTA')

from src.pipeline.validate_crossref import run_validation, get_valid_symbols, TABLES_WITH_SYMBOL

con = duckdb.connect('d:/VESTA/db/vesta_latest_backup.duckdb', read_only=True)
valid_symbols = get_valid_symbols(con)
print(f"Total valid symbols in core.dim_symbol: {len(valid_symbols)}")

report = run_validation(con)

print("\n=== BREAKDOWN OF ORPHAN SYMBOLS PER TABLE ===")
for table_name, orphans in report['orphan_symbols'].items():
    print(f"\nTable: {table_name}")
    print(f"  Total orphan symbols: {len(orphans)}")
    # Sample orphans
    print(f"  Sample orphans (first 10): {orphans[:10]}")
    
    # Classify orphans: Covered Warrants (CW: starts with C), Bonds (ends with number or starts with bond prefix), ETF (starts with FU or E1), Normal Equities
    cw = [s for s in orphans if s.startswith('C') and len(s) == 8]
    bonds = [s for s in orphans if any(char.isdigit() for char in s[3:]) and len(s) >= 8 and not s.startswith('C')]
    etfs = [s for s in orphans if s.startswith('FU') or s.startswith('E1')]
    others = [s for s in orphans if s not in cw and s not in bonds and s not in etfs]
    
    print(f"  Classification: Covered Warrants={len(cw)}, Bonds={len(bonds)}, ETFs={len(etfs)}, Other Equities={len(others)}")
    if others:
        print(f"  Other Equities: {others[:20]}")

print("\n=== FUTURE TIMESTAMPS ===")
print(report['future_timestamps'])

print("\n=== ORPHAN ADJUSTMENT EVENTS ===")
print(report['orphan_adjustment_events'])

# Specifically check fundamentals, market_ohlcv_daily, and news
print("\n=== CHECKING SPECIFIC TARGET TABLES ===")
for tbl in ['core.fundamentals', 'core.market_ohlcv_daily', 'core.news', 'core.corporate_events', 'core.realtime_quote_snapshot']:
    orphans = report['orphan_symbols'].get(tbl, [])
    print(f"{tbl:<35}: {len(orphans)} orphans")
    if tbl == 'core.fundamentals':
        print(f"   -> fundamentals orphans: {orphans}")

con.close()
