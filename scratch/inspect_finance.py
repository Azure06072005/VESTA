import sys, io
sys.stdout.reconfigure(encoding="utf-8")
from vnstock_data import Finance, Fundamental

print("--- 1. Testing Fundamental().equity('FPT') ---")
fund = Fundamental().equity("FPT")
for m in ["income_statement", "balance_sheet", "cash_flow", "ratio"]:
    try:
        df = getattr(fund, m)(period="quarter")
        print(f"Fundamental.{m}: shape={df.shape}, cols={df.columns.tolist()[:6]}")
    except Exception as e:
        print(f"Fundamental.{m} error:", e)

print("\n--- 2. Testing Finance(symbol='FPT', source='KBS') ---")
fin = Finance(symbol="FPT", source="KBS")
for m in ["income_statement", "balance_sheet", "cash_flow", "ratio"]:
    try:
        df = getattr(fin, m)(period="quarter")
        print(f"Finance.{m}: shape={df.shape}, cols={df.columns.tolist()[:6]}")
    except Exception as e:
        print(f"Finance.{m} error:", e)
