import os, sys, json, pathlib
sys.stdout.reconfigure(encoding="utf-8")
if not os.environ.get("VNSTOCK_API_KEY"):
    key_path = pathlib.Path.home() / ".vnstock" / "api_key.json"
    if key_path.exists():
        with open(key_path, "r", encoding="utf-8") as f:
            os.environ["VNSTOCK_API_KEY"] = json.load(f).get("api_key", "")
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
