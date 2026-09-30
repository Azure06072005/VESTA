"""scratch/inspect_cafef_news_ashx.py
Kiểm tra chi tiết JSON trả về từ endpoint News.ashx trong các file HAR.
"""
import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

HAR_DIR = Path("scratch/har/cafef")
har_path = HAR_DIR / "cafef_du-lieu_tintuc.har"

with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
    har_data = json.load(f)

entries = har_data.get("log", {}).get("entries", [])
print(f"Tổng số entries trong {har_path.name}: {len(entries)}")

for entry in entries:
    url = entry.get("request", {}).get("url", "")
    if "News.ashx" in url:
        resp_text = entry.get("response", {}).get("content", {}).get("text", "")
        print("\n" + "=" * 80)
        print("URL:", url)
        try:
            d = json.loads(resp_text)
            data_list = d.get("Data", [])
            print(f"Số lượng tin trong mảng Data: {len(data_list)}")
            if data_list:
                item = data_list[0]
                print("Các keys của 1 bài tin:", list(item.keys()))
                for k, v in item.items():
                    print(f"  {k}: {str(v)[:120]}")
        except Exception as e:
            print("Lỗi parse JSON:", e)
            print("Raw text:", resp_text[:200])
        break
