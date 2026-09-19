import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
os.environ['VNSTOCK_API_KEY'] = 'vnstock_f84ed9f3014e77c53a88e3eae1bc1be8'

from vnstock_data import Fundamental

fun = Fundamental()
df_ratio = fun.equity('VCB').ratio()
print(f"Total ratio items: {len(df_ratio)}")
items = df_ratio[['id', 'name', 'unit']].drop_duplicates()
print(f"Unique ratio metrics: {len(items)}")
for _, row in items.iterrows():
    print(f" - {row['id']}: {row['name']} ({row['unit']})")
