import requests
from bs4 import BeautifulSoup
from urllib.parse import urlsplit, urlunsplit
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
})

print("Testing SBV news list fetch...")
time.sleep(2)
list_url = (
    "https://sbv.gov.vn/vi/tin-tuc-su-kien?"
    "p_p_id=com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_jaxi"
    "&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
    "&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_jaxi_delta=12"
    "&p_r_p_resetCur=false&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_jaxi_cur=1"
)
resp = s.get(list_url, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

news_items = []
for a in soup.find_all("a", class_="title-news-link"):
    title = a.get_text(strip=True)
    raw_href = a.get("href", "")
    # Strip redirect parameter
    parts = urlsplit(raw_href)
    clean_href = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    
    # Try to find date in parent
    parent = a.find_parent("div")
    date_text = None
    if parent:
        date_el = parent.find(class_=lambda c: c and any(k in c.lower() for k in ["date", "publish"]))
        if date_el:
            date_text = date_el.get_text(strip=True)
            
    news_items.append({"title": title, "url": clean_href, "date_text": date_text})

print(f"Extracted {len(news_items)} items from SBV page 1:")
for item in news_items[:3]:
    print(f"  Title: {item['title'][:50]} | Date: {item['date_text']} | URL: {item['url'][:60]}...")

if news_items:
    sample_url = news_items[0]["url"]
    print(f"\nFetching sample detail page: {sample_url}")
    time.sleep(2)
    art_resp = s.get(sample_url, timeout=15)
    art_soup = BeautifulSoup(art_resp.text, "html.parser")
    print(f"Article response status: {art_resp.status_code}, len: {len(art_resp.text)}")
    print(f"Article title: {art_soup.title.string if art_soup.title else 'None'}")
