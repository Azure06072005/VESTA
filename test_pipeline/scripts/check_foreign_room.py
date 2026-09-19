import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
os.environ['VNSTOCK_API_KEY'] = 'vnstock_f84ed9f3014e77c53a88e3eae1bc1be8'

# Check legacy vnstock
try:
    from vnstock import stock_screening_insights, financial_ratio, listing_companies
    print("legacy vnstock imported")
    df_list = listing_companies()
    print("listing_companies cols:", [c for c in df_list.columns if 'foreign' in c.lower() or 'room' in c.lower()][:10])
except Exception as e:
    print("Legacy error:", e)

# Check vnstock_data
try:
    from vnstock_data import Reference
    ref = Reference()
    symbols_df = ref.equity.list_by_exchange()
    print("ref.equity.list_by_exchange cols:", symbols_df.columns.tolist())
    print(symbols_df.head(2).to_dict())
except Exception as e:
    print("vnstock_data error:", e)
