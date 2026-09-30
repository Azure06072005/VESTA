"""scratch/inspect_har_cafef.py

Khảo sát chuyên sâu cấu trúc các file .har của CafeF trong scratch/har/cafef/
"""
import sys
import os
import json
from pathlib import Path
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

HAR_DIR = Path("scratch/har/cafef")
har_files = list(HAR_DIR.glob("*.har"))

print("=" * 80)
print(f"TÌM THẤY {len(har_files)} FILE .HAR TRONG {HAR_DIR}:")
for h in har_files:
    size_mb = h.stat().st_size / (1024 * 1024)
    print(f"  • {h.name} ({size_mb:.2f} MB)")

print("\n" + "=" * 80)
print("QUÉT CÁC ENDPOINT TIN TỨC VÀ NỘI DUNG BODY TRONG FILE HAR TIN TỨC:")

target_hars = [
    HAR_DIR / "cafef_du-lieu_tintuc.har",
    HAR_DIR / "cafef_du-lieu_tintuc_sample.har",
    HAR_DIR / "cafef_ttck.har",
    HAR_DIR / "cafef_dn.har",
]

for h_path in target_hars:
    if not h_path.exists():
        continue
    print(f"\n---> ĐANG PHÂN TÍCH: {h_path.name} ({h_path.stat().st_size / 1024 / 1024:.2f} MB)...")
    try:
        with open(h_path, "r", encoding="utf-8", errors="ignore") as f:
            har_data = json.load(f)
    except Exception as e:
        print(f"  [Lỗi đọc HAR]: {e}")
        continue

    entries = har_data.get("log", {}).get("entries", [])
    print(f"  Tổng số entries (HTTP transactions): {len(entries)}")

    news_entries = []
    html_articles = []
    ajax_news = []

    for entry in entries:
        req = entry.get("request", {})
        resp = entry.get("response", {})
        url = req.get("url", "")
        mime = resp.get("content", {}).get("mimeType", "")
        text = resp.get("content", {}).get("text", "")

        # 1. AJAX news list
        if "News.ashx" in url or "Events_RelatedNews" in url or "ajaxcongbothongtin" in url:
            ajax_news.append((url, text[:300]))

        # 2. Trang chi tiết bài báo HTML (.chn)
        if (".chn" in url and "cafef.vn" in url and not url.endswith("Event.chn") and not "ajax" in url.lower() and "du-lieu" not in url):
            if "text/html" in mime and len(text) > 1000:
                html_articles.append((url, text))

    print(f"  • Số lượng AJAX News List calls: {len(ajax_news)}")
    print(f"  • Số lượng Trang Chi Tiết Bài Báo HTML (.chn) có content: {len(html_articles)}")

    if ajax_news:
        print("\n  [MẪU AJAX NEWS LIST]:")
        url_sample, txt_sample = ajax_news[0]
        print(f"  URL: {url_sample}")
        print(f"  Preview: {txt_sample}")

    if html_articles:
        print("\n  [MẪU NỘI DUNG CHI TIẾT BÀI BÁO HTML TRONG HAR]:")
        art_url, art_html = html_articles[0]
        print(f"  URL bài viết: {art_url}")
        soup = BeautifulSoup(art_html, "html.parser")
        
        # Thử trích xuất body theo các selector của CafeF
        title = soup.find("h1")
        title_text = title.get_text(strip=True) if title else "No H1"
        
        # Các selector nội dung bài báo của CafeF
        content_div = soup.find("div", class_="detail-content") or soup.find("div", class_="contentcontent") or soup.find("div", id="mainContent")
        if content_div:
            body_text = content_div.get_text("\n", strip=True)
            print(f"  Tiêu đề (H1): {title_text}")
            print(f"  Độ dài Body trích xuất được: {len(body_text)} ký tự")
            print(f"  Đoạn trích Body 300 ký tự đầu:")
            print("  " + "-" * 60)
            print("  " + body_text[:300].replace("\n", " "))
            print("  " + "-" * 60)
        else:
            print("  Không tìm thấy div nội dung bài viết chuẩn!")
