import os, sys
sys.stdout.reconfigure(encoding="utf-8")

api_key = os.environ.get("VNSTOCK_API_KEY")
if not api_key:
    raise SystemExit("Set VNSTOCK_API_KEY env var first -- never hardcode credentials in this file.")

sys.path.insert(0, "src")
import vnstock

vnstock.change_api_key(api_key)

fund = vnstock.Fundamental().equity("FPT")
for m in ["income_statement", "balance_sheet", "cash_flow", "ratio"]:
    try:
        df = getattr(fund, m)()
        if hasattr(df, "shape"):
            print(f"=== {m} ===")
            print("Shape:", df.shape)
            print("Columns:", df.columns.tolist()[:8])
            print("Head:\n", df.head(2))
        else:
            print(f"=== {m} ===: non-dataframe", type(df))
    except Exception as e:
        print(f"=== {m} === error:", e)