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

resp = s.get("https://sbv.gov.vn/vi/tin-tuc-su-kien", timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

news_links = soup.find_all("a", class_="title-news-link")
print(f"News links found: {len(news_links)}")
for i, a in enumerate(news_links):
    print(f"{i+1}. {a.get_text(strip=True)} -> {a.get('href')}")

# Also check surrounding card or parent container for date, summary
if news_links:
    first_parent = news_links[0].find_parent()
    print("\n--- First article parent sample ---")
    print(first_parent.prettify()[:600])
