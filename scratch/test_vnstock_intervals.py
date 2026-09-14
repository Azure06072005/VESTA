"""scratch/test_vnstock_intervals.py

Tests whether vnstock_data (Silver Tier) supports intervals: 1s, 5s, 30s, 1m, 1d, and intraday ticks
"""
import sys
import os

# Set UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

print("=" * 80)
print("TESTING VNSTOCK_DATA (SILVER TIER) INTERVALS & RESOLUTIONS")
print("=" * 80)

try:
    from vnstock_data import Market, show_api, show_doc
    print("-> Successfully imported vnstock_data!")
except Exception as e:
    print(f"Error importing vnstock_data: {e}")
    sys.exit(1)

mkt = Market()

# 1. Inspect API definition and documentation for ohlcv and intraday
print("\n[1] EXPLORING API METHODS FOR Market.equity:")
try:
    eq = mkt.equity("FPT")
    methods = [m for m in dir(eq) if not m.startswith("_")]
    print("Available methods on Market.equity('FPT'):", methods)
except Exception as e:
    print("Error inspecting Market.equity:", e)

# 2. Test intervals on ohlcv
test_intervals = ["1s", "5s", "30s", "1m", "5m", "15m", "30m", "1H", "1D", "1W", "1M"]
symbol = "FPT"

print(f"\n[2] TESTING OHLCV INTERVALS FOR SYMBOL '{symbol}':")
for interval in test_intervals:
    try:
        df = mkt.equity(symbol).ohlcv(interval=interval, count=5)
        if df is not None and not df.empty:
            print(f" -> Interval '{interval:<4}': SUCCESS! Returned {len(df)} rows. Sample timestamp: {df.index[0] if hasattr(df, 'index') else df.iloc[0, 0]}")
        else:
            print(f" -> Interval '{interval:<4}': EMPTY RESULT (None or 0 rows).")
    except Exception as e:
        err_msg = str(e).strip().replace("\n", " ")
        print(f" -> Interval '{interval:<4}': FAILED! Error: {err_msg[:90]}")

# 3. Test intraday / tick data
print(f"\n[3] TESTING INTRADAY / TICK DATA FOR SYMBOL '{symbol}':")
try:
    if hasattr(mkt.equity(symbol), "intraday"):
        df_intra = mkt.equity(symbol).intraday()
        print(f" -> mkt.equity('{symbol}').intraday(): SUCCESS! Shape: {df_intra.shape}")
        print("    Columns:", list(df_intra.columns))
        print("    Sample rows:")
        print(df_intra.head(3).to_string())
    else:
        print(f" -> mkt.equity('{symbol}') has NO 'intraday' method.")
except Exception as e:
    print(f" -> mkt.equity('{symbol}').intraday() Error:", e)

# 4. Test price board / realtime quote
print(f"\n[4] TESTING REALTIME / QUOTE FOR SYMBOL '{symbol}':")
try:
    if hasattr(mkt.equity(symbol), "quote"):
        df_quote = mkt.equity(symbol).quote()
        print(f" -> mkt.equity('{symbol}').quote(): SUCCESS! Shape: {df_quote.shape if hasattr(df_quote, 'shape') else type(df_quote)}")
    elif hasattr(mkt.equity(symbol), "price"):
        df_price = mkt.equity(symbol).price()
        print(f" -> mkt.equity('{symbol}').price(): SUCCESS!")
except Exception as e:
    print(f" -> quote/price Error:", e)

print("\n" + "=" * 80)
print("TEST COMPLETED!")
print("=" * 80)
