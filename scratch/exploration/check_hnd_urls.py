import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

# Test different URL patterns for page 2
for test_url in [
    "http://www.hoinongdan.org.vn/chinh-sach?page=2",
    "http://www.hoinongdan.org.vn/chinh-sach?p=2",
    "http://www.hoinongdan.org.vn/chinh-sach/trang-2",
    "http://www.hoinongdan.org.vn/chinh-sach/p2",
]:
    r = s.get(test_url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    # Find active or current page
    active = soup.find(class_=lambda c: c and "active" in c.lower() and "page" in c.lower())
    print(f"URL: {test_url} -> Status: {r.status_code}, Active page: {active.get_text(strip=True) if active else 'None'}")
