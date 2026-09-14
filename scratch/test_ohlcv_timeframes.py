"""scratch/test_ohlcv_timeframes.py

Tests OHLCV with proper length parameter across intervals: 1s, 5s, 30s, 1m, 5m, 15m, 1H, 1D
"""
import sys
from vnstock_data import Market

sys.stdout.reconfigure(encoding="utf-8")
mkt = Market()

print("=" * 80)
print("TESTING OHLCV INTERVALS WITH length='1M'")
print("=" * 80)

intervals_to_test = ["1s", "5s", "30s", "1m", "5m", "15m", "1H", "1D"]
for itv in intervals_to_test:
    try:
        df = mkt.equity("FPT").ohlcv(length="1M", interval=itv)
        if df is not None and not df.empty:
            print(f" -> Interval '{itv:<4}': [SUCCESS] Shape={df.shape}. Columns={list(df.columns)}")
            print(f"    First row time: {df.index[0] if hasattr(df, 'index') else df.iloc[0,0]}")
        else:
            print(f" -> Interval '{itv:<4}': [EMPTY] (0 rows)")
    except Exception as e:
        print(f" -> Interval '{itv:<4}': [FAILED] {e}")

print("\n" + "=" * 80)
print("TESTING INTRADAY TICK-BY-TICK (RESAMPLING TO 1s, 5s, 30s)")
print("=" * 80)
df_ticks = mkt.equity("FPT").intraday()
print(f"Intraday ticks returned: {len(df_ticks)} trades.")
print(df_ticks.head(5).to_string())

# Demonstrate resampling ticks into 1s, 5s, 30s bars
import pandas as pd
df_ticks['time'] = pd.to_datetime(df_ticks['time'])
df_ticks = df_ticks.sort_values('time')
df_ticks.set_index('time', inplace=True)

for freq in ['1s', '5s', '30s', '1min']:
    df_bars = df_ticks['price'].resample(freq).ohlc().dropna()
    print(f"\nResampled ticks into {freq} OHLC bars (Count={len(df_bars)}):")
    print(df_bars.head(3))
