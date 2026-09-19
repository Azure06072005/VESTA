import os
import sys
import json
import inspect
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
os.environ["VNSTOCK_API_KEY"] = "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"

from vnstock_data import Market, Fundamental, Reference

print("=" * 80)
print("VNSTOCK DATA API INSPECTION & GAP ANALYSIS (SILVER TIER)")
print("=" * 80)

mkt = Market()
fun = Fundamental()
ref = Reference()

def inspect_obj(obj, name):
    print(f"\n--- Methods on {name} ---")
    methods = [m for m in dir(obj) if not m.startswith("_")]
    print(", ".join(methods))
    return methods

mkt_methods = inspect_obj(mkt, "Market")
fun_methods = inspect_obj(fun, "Fundamental")
ref_methods = inspect_obj(ref, "Reference")

print("\n--- Methods on Market.equity('VCB') ---")
try:
    eq = mkt.equity("VCB")
    eq_methods = [m for m in dir(eq) if not m.startswith("_")]
    print(", ".join(eq_methods))
except Exception as e:
    print("Error:", e)

print("\n--- Methods on Fundamental.equity('VCB') ---")
try:
    feq = fun.equity("VCB")
    feq_methods = [m for m in dir(feq) if not m.startswith("_")]
    print(", ".join(feq_methods))
except Exception as e:
    print("Error:", e)

print("\n--- Methods on Reference ---")
ref_methods = [m for m in dir(ref) if not m.startswith("_")]
print(", ".join(ref_methods))
