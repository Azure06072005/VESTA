import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

url = "http://www.hoinongdan.org.vn/chinh-sach/du-thao-luat-dat-dai-sua-doi-rut-gan-160-dieu-chu-trong-sinh-ke-nguoi-dan-381436"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
soup = BeautifulSoup(r.text, "html.parser")

for d in soup.find_all(["div", "article", "section"]):
    classes = " ".join(d.get("class", []))
    txt = d.get_text(strip=True)
    if any(k in classes.lower() for k in ["detail", "content", "news", "article", "main", "body"]):
        if len(txt) > 500:
            print(f"Tag <{d.name} class='{classes}'> len={len(txt)}")
            print(f"Snippet: {txt[:250]}...\n")
