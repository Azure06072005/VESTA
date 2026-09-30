import os
import sys
from vnstock.api.quote import Quote
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

for src in ['kbs', 'vci']:
    print(f"\n================ TESTING SOURCE: {src} ================")
    q = Quote(symbol='FPT', source=src)
    
    # Test 1: Recent 1m data
    try:
        df_rec = q.history(start='2026-09-20', end='2026-09-25', interval='1m')
        print(f"[{src}] 2026-09-20 to 2026-09-25 (1m): rows={len(df_rec)}")
        if not df_rec.empty:
            print(f"   min={df_rec['time'].min()}, max={df_rec['time'].max()}")
            print(df_rec.head(1))
    except Exception as e:
        print(f"[{src}] Error recent: {e}")

    # Test 2: 1 year ago (2025)
    try:
        df_2025 = q.history(start='2025-06-01', end='2025-06-05', interval='1m')
        print(f"[{src}] 2025-06-01 to 2025-06-05 (1m): rows={len(df_2025)}")
        if not df_2025.empty:
            print(f"   min={df_2025['time'].min()}, max={df_2025['time'].max()}")
    except Exception as e:
        print(f"[{src}] Error 2025: {e}")

    # Test 3: 2 years ago (2024)
    try:
        df_2024 = q.history(start='2024-06-01', end='2024-06-05', interval='1m')
        print(f"[{src}] 2024-06-01 to 2024-06-05 (1m): rows={len(df_2024)}")
        if not df_2024.empty:
            print(f"   min={df_2024['time'].min()}, max={df_2024['time'].max()}")
    except Exception as e:
        print(f"[{src}] Error 2024: {e}")

    # Test 4: 3 years ago (2023)
    try:
        df_2023 = q.history(start='2023-06-01', end='2023-06-05', interval='1m')
        print(f"[{src}] 2023-06-01 to 2023-06-05 (1m): rows={len(df_2023)}")
        if not df_2023.empty:
            print(f"   min={df_2023['time'].min()}, max={df_2023['time'].max()}")
    except Exception as e:
        print(f"[{src}] Error 2023: {e}")
