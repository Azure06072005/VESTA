import os
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
os.environ["VNSTOCK_API_KEY"] = "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"

from vnstock_data import Market, Fundamental, Reference

mkt = Market()
fun = Fundamental()
ref = Reference()

print("=== METHODS ON ref.company('VCB') ===")
try:
    c = ref.company("VCB")
    print("Methods:", [m for m in dir(c) if not m.startswith("_")])
    for m in ["overview", "profile", "shareholders", "officers", "subsidiaries"]:
        if hasattr(c, m):
            res = getattr(c, m)()
            print(f"\n--- {m} ---")
            if isinstance(res, pd.DataFrame):
                print(res.head(2).to_string())
            elif isinstance(res, dict):
                print({k: str(v)[:80] for k, v in list(res.items())[:10]})
            else:
                print(type(res), res)
except Exception as e:
    print("Error:", e)

print("\n=== METHODS ON ref.equity ===")
try:
    eq_ref = ref.equity
    print("Methods:", [m for m in dir(eq_ref) if not m.startswith("_")])
    for m in ["listing", "symbols", "sectors", "industries"]:
        if hasattr(eq_ref, m):
            res = getattr(eq_ref, m)()
            print(f"\n--- ref.equity.{m}() ---")
            if isinstance(res, pd.DataFrame):
                print("Cols:", res.columns.tolist())
                print(res.head(2).to_string())
except Exception as e:
    print("Error:", e)

print("\n=== METHODS ON ref.bond ===")
try:
    b_ref = ref.bond
    print("Methods:", [m for m in dir(b_ref) if not m.startswith("_")])
    for m in ["listing", "symbols", "types"]:
        if hasattr(b_ref, m):
            res = getattr(b_ref, m)()
            print(f"\n--- ref.bond.{m}() ---")
            if isinstance(res, pd.DataFrame):
                print("Cols:", res.columns.tolist())
                print(res.head(2).to_string())
except Exception as e:
    print("Error:", e)

print("\n=== METHODS ON ref.market ===")
try:
    m_ref = ref.market
    print("Methods:", [m for m in dir(m_ref) if not m.startswith("_")])
    for m in ["trading_calendar", "holidays", "status"]:
        if hasattr(m_ref, m):
            res = getattr(m_ref, m)()
            print(f"\n--- ref.market.{m}() ---")
            if isinstance(res, pd.DataFrame):
                print(res.head(2).to_string())
except Exception as e:
    print("Error:", e)
