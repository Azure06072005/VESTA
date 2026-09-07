import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

url = (
    "https://www.horea.org.vn/hoat-dong-horea/"
    "Cong-van-1102026CV-HoREA-ngay-03-thang-09-nam-2026-"
    "De-xuat-hoan-thien-chinh-sach-phap-luat-dieu-chinh-cac-loai-bat-dong-san-dua-vao-kinh-doanh-la-cong-trinh-xay-dung-co-cong-nang-phuc-vu-muc-dich-van-phong-du-lich-luu-tru-trong-du-thao-Luat-Kinh-doan.html"
)

resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

print("Article Title (title tag):", soup.title.string if soup.title else "None")

# Find h1, h2, or title div
h1 = soup.find("h1")
print("H1:", h1.get_text(strip=True) if h1 else "No H1")

# Look for date
for div in soup.find_all(["div", "span", "p"]):
    t = div.get_text(strip=True)
    if "ngày" in t.lower() and any(c.isdigit() for c in t) and len(t) < 80:
        print(f"Date candidate: {t}")
        break

# Look for main content container
for c in ["content", "detail", "item-content", "body", "article"]:
    found = soup.find(class_=lambda cls: cls and c in cls.lower())
    if found and len(found.get_text(strip=True)) > 200:
        print(f"Found content container with class='{found.get('class')}': length={len(found.get_text(strip=True))}")
        print(f"Content snippet: {found.get_text(separator=' ', strip=True)[:300]}...")
        break
