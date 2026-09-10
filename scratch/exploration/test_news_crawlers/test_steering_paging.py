import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

for param in ["p_page", "page", "p", "CurrentPage"]:
    url = f"http://www.hoinongdan.org.vn/?pageid=27205&p_cate=11495&{param}=2"
    r = s.get(url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    cur = soup.find(class_=lambda c: c and "currentpage" in c.lower())
    print(f"Param {param}=2 -> CurrentPage: {cur.get_text(strip=True) if cur else 'None'}")
