import sys
import io
import pathlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "src"))

from src.service.console_api import (
    get_dashboard_overview,
    get_foreign_flow,
    get_multi_asset_summary,
    get_market_heatmap
)

print("=== 1. get_dashboard_overview() ===")
ov = get_dashboard_overview()
print("Latest date:", ov.get("latest_trading_date"))
print("Market summary:", ov.get("market_summary"))

print("\n=== 2. get_foreign_flow(5) ===")
ff = get_foreign_flow(5)
print("Count:", ff.get("count"))
for r in ff.get("data", []):
    print(" ", r)

print("\n=== 3. get_multi_asset_summary() ===")
ma = get_multi_asset_summary()
print("Derivatives count:", len(ma.get("derivatives", [])))
for d in ma.get("derivatives", []):
    print(" ", d)
print("ETFs count:", len(ma.get("etfs", [])))
for e in ma.get("etfs", [])[:3]:
    print(" ", e)
print("CWs count:", len(ma.get("covered_warrants", [])))
for c in ma.get("covered_warrants", [])[:3]:
    print(" ", c)

print("\n=== 4. get_market_heatmap(5) ===")
hm = get_market_heatmap(5)
print("Heatmap date:", hm.get("date"), "count:", hm.get("count"))
for h in hm.get("data", []):
    print(" ", h["symbol"], "price:", h["last_price"], "val_bil:", h["trading_value_billion"], "pct:", h["pct_change"])
