import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

url = "https://vita.vn/vi/news/hiep-hoi-du-lich-tinh-thanh-hoa-ket-noi-giao-thuong-cung-doanh-nghiep-du-lich-philippines-va-han-quoc-272.html"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

h1 = soup.find("h1")
if h1:
    parent = h1.find_parent()
    print("Parent of H1:", parent.name, parent.get("class"))
    # Print next siblings
    sibs = h1.find_next_siblings()
    print(f"Siblings of H1: {len(sibs)}")
    for s in sibs[:5]:
        print(f"  <{s.name} class='{s.get('class')}'> len={len(s.get_text(strip=True))}")
        print(f"    {s.get_text(strip=True)[:150]}...")
