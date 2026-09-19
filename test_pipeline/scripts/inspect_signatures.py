import os
import sys
import inspect

sys.stdout.reconfigure(encoding='utf-8')
os.environ["VNSTOCK_API_KEY"] = "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"

from vnstock_data import Market, Fundamental, Reference

mkt = Market()
fun = Fundamental()
ref = Reference()

eq = mkt.equity("VCB")
feq = fun.equity("VCB")

funcs = [
    ("mkt.equity.order_book", getattr(eq, "order_book", None)),
    ("mkt.equity.price_depth", getattr(eq, "price_depth", None)),
    ("mkt.equity.trades", getattr(eq, "trades", None)),
    ("mkt.equity.intraday", getattr(eq, "intraday", None)),
    ("mkt.equity.proprietary_flow", getattr(eq, "proprietary_flow", None)),
    ("mkt.equity.foreign_flow", getattr(eq, "foreign_flow", None)),
    ("fun.equity.note", getattr(feq, "note", None)),
    ("fun.equity.filing", getattr(feq, "filing", None)),
    ("ref.bond", getattr(ref, "bond", None)),
    ("ref.equity", getattr(ref, "equity", None)),
    ("ref.company", getattr(ref, "company", None)),
    ("ref.market", getattr(ref, "market", None)),
]

for name, f in funcs:
    print("=" * 60)
    print(f"FUNCTION: {name}")
    if f is None:
        print(" -> NOT FOUND")
        continue
    try:
        sig = inspect.signature(f)
        print(f" -> Signature: {sig}")
    except Exception as e:
        print(f" -> Signature error: {e}")
    doc = inspect.getdoc(f)
    if doc:
        print(f" -> Docstring:\n{doc[:300]}...")
    else:
        print(" -> No docstring")
