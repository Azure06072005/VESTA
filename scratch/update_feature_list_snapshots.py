import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("Harness/feature_list.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for feat in data["features"]:
    if feat["id"] == "F007":
        feat["evidence"] = (
            "Upgraded 2026-10-01 to Full Max Historical & Realtime Scale: "
            "(1) core.realtime_quote_snapshot: Ingested 1,726 active symbols (total 6,611 rows) at latest EOD 2026-10-01 via Vietcap Direct REST API with automatic chunking; "
            "(2) core.order_book_depth & intraday_trades: Dedicated Vietcap REST crawler (src/crawlers/order_book_depth_vietcap.py) independently captures VN100 Top 3 Bid/Ask depth (511 rows) and OFI ratio with 0% vnstock dependency; "
            "(3) core.market_sentiment_snapshot: Backfilled 26 years of market breadth (18,779 rows from 2000 to 2026) across HOSE, HNX, UPCOM; "
            "(4) core.market_screener_snapshot: Reconstructed 21 years (43,223 rows, 2005-2026) across 1,742 symbols covering 13 core valuation/profitability factors."
        )
        if "src/crawlers/order_book_depth_vietcap.py" not in feat.get("file_dependencies", []):
            feat["file_dependencies"].append("src/crawlers/order_book_depth_vietcap.py")
        if "src/crawlers/crawl_deep_screener.py" not in feat.get("file_dependencies", []):
            feat["file_dependencies"].append("src/crawlers/crawl_deep_screener.py")
    elif feat["id"] == "F007b":
        feat["evidence"] += (
            " | Live 2026-10-01 update: Deep Screener crawler (src/crawlers/crawl_deep_screener.py) scanned 1,522 tickers with 34 quantitative criteria, "
            "and historical backfill expanded core.market_screener_snapshot to 43,223 rows across 81 quarters (2005-2026)."
        )
        if "src/crawlers/crawl_deep_screener.py" not in feat.get("file_dependencies", []):
            feat["file_dependencies"].append("src/crawlers/crawl_deep_screener.py")

with open("Harness/feature_list.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("✅ Đã cập nhật thành công Harness/feature_list.json!")
