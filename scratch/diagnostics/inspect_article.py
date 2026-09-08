import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
})

url = "https://sbv.gov.vn/vi/w/408.000-t%E1%BB%B7-%C4%91%E1%BB%93ng-s%E1%BA%B5n-s%C3%A0ng-ti%E1%BA%BFp-s%E1%BB%A9c-cho-c%C3%A1c-%C4%91%E1%BB%99ng-l%E1%BB%B1c-t%C4%83ng-tr%C6%B0%E1%BB%9Fng-kinh-t%E1%BA%BF-v%C3%A0-doanh-nghi%E1%BB%87p-nh%E1%BB%8F-v%C3%A0-v%E1%BB%ABa"
resp = s.get(url, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

matching = soup.find_all(lambda tag: tag.has_attr("class") and any(k in " ".join(tag["class"]).lower() for k in ["content", "detail", "article"]))
for m in matching[:5]:
    print(f"Tag: <{m.name} class='{' '.join(m.get('class', []))}'>")
    print(f"Text snippet: {m.get_text(strip=True)[:150]}\n")
