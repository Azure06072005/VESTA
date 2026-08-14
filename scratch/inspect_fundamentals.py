import os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.environ["VNSTOCK_API_KEY"] = "vnstock_85ab49abed2035a64e3bdb0f7dc0467a"
sys.path.insert(0, "src")
import vnstock

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
