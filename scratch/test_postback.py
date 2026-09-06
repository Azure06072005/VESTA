import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

url = "http://www.hoinongdan.org.vn/?pageid=27205&p_cate=11495"
r1 = s.get(url, timeout=15)
soup1 = BeautifulSoup(r1.text, "html.parser")

viewstate = soup1.find("input", id="__VIEWSTATE")["value"]
eventvalidation = soup1.find("input", id="__EVENTVALIDATION")["value"] if soup1.find("input", id="__EVENTVALIDATION") else ""

payload = {
    "__EVENTTARGET": "ctrl_191570_58$pager$ctl01$ctl01",
    "__EVENTARGUMENT": "",
    "__VIEWSTATE": viewstate,
}
if eventvalidation:
    payload["__EVENTVALIDATION"] = eventvalidation

r2 = s.post(url, data=payload, timeout=15)
soup2 = BeautifulSoup(r2.text, "html.parser")

cur = soup2.find(class_=lambda c: c and "currentpage" in c.lower())
print("Page 2 CurrentPage via PostBack:", cur.get_text(strip=True) if cur else "None")
links = [(a.get_text(strip=True), a['href']) for a in soup2.find_all('a', href=True) if 'p_steering=' in a['href']]
print("Steering links on Page 2:", len(links))
for t, h in links[:3]:
    print(f"  {t[:60]} -> {h}")
