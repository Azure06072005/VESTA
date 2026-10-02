import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding='utf-8')

from src.crawlers.market_insights import fetch_screener_criteria

criteria = fetch_screener_criteria()
print(f"Tổng số tiêu chí hỗ trợ bởi Vietcap Screener: {len(criteria)}")
print("Danh sách các trường:")
for idx, r in criteria.iterrows():
    print(f"  {r['category']:<15} | {r['field_name']:<25} -> {r['readable_name']}")
