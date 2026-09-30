import sys, pathlib
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(pathlib.Path('src').resolve()))
from etl import db
db.load_env()
import vnstock_data as vs

listing = vs.Listing(source='vci')
df = listing.industries_icb()

# Let's inspect all L1 and L2 to establish the exact parent mapping
l1_df = df[df['level'] == 1].copy()
l2_df = df[df['level'] == 2].copy()
l3_df = df[df['level'] == 3].copy()
l4_df = df[df['level'] == 4].copy()

print("L1 codes:", l1_df['icb_code'].tolist())
print("L2 codes:", l2_df['icb_code'].tolist())

# Check how L4 links to L3, L3 to L2, L2 to L1
# In ICB standards:
# L4 (4 digits) -> L3 is first 3 digits + '0' (e.g. 0533 -> 0530)
# L3 (4 digits) -> L2 is first 2 digits + '00' (e.g. 0530 -> 0500)
# L2 -> L1:
# 0500 -> 0001 (Oil & Gas)
# 1300, 1700 -> 1000 (Basic Materials)
# 2300, 2700 -> 2000 (Industrials)
# 3300, 3500, 3700 -> 3000 (Consumer Goods)
# 4500 -> 4000 (Health Care)
# 5300, 5500, 5700 -> 5000 (Consumer Services)
# 6500 -> 6000 (Telecommunications)
# 7500 -> 7000 (Utilities)
# 8300, 8500, 8600, 8700, 8900 -> 8000 (Financials)
# 9500 -> 9000 (Technology)

l2_to_l1 = {
    '0500': '0001',
    '1300': '1000',
    '1700': '1000',
    '2300': '2000',
    '2700': '2000',
    '3300': '3000',
    '3500': '3000',
    '3700': '3000',
    '4500': '4000',
    '5300': '5000',
    '5500': '5000',
    '5700': '5000',
    '6500': '6000',
    '7500': '7000',
    '8300': '8000',
    '8500': '8000',
    '8600': '8000',
    '8700': '8000',
    '8900': '8000',
    '9500': '9000',
}

# Verify every L2 has an L1
unmapped_l2 = [c for c in l2_df['icb_code'] if c not in l2_to_l1]
print("Unmapped L2:", unmapped_l2)

# Verify L3 -> L2
l3_unmapped = []
for c in l3_df['icb_code']:
    parent_l2 = c[:2] + '00'
    if parent_l2 not in l2_to_l1:
        l3_unmapped.append((c, parent_l2))
print("Unmapped L3 -> L2:", l3_unmapped)

# Verify L4 -> L3
l3_codes = set(l3_df['icb_code'])
l4_unmapped = []
for c in l4_df['icb_code']:
    parent_l3 = c[:3] + '0'
    if parent_l3 not in l3_codes:
        l4_unmapped.append((c, parent_l3))
print("Unmapped L4 -> L3:", l4_unmapped)
