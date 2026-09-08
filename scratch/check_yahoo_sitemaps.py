import requests
import xml.etree.ElementTree as ET
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

# 1. Test robots.txt for sitemap location
print("=== 1. Checking robots.txt for Yahoo Finance ===")
try:
    r = requests.get('https://finance.yahoo.com/robots.txt', headers=headers, timeout=10)
    print("robots.txt status:", r.status_code)
    for line in r.text.splitlines():
        if 'sitemap' in line.lower():
            print(" ", line)
except Exception as e:
    print("Error:", e)

# 2. Test common Yahoo sitemap index URLs
sitemap_candidates = [
    "https://finance.yahoo.com/sitemap.xml",
    "https://finance.yahoo.com/sitemaps/finance-sitemap_index_US_en-US.xml",
    "https://finance.yahoo.com/news/sitemap.xml",
    "https://www.yahoo.com/news/sitemap.xml"
]

print("\n=== 2. Testing Sitemap Candidates ===")
for sm in sitemap_candidates:
    try:
        r = requests.get(sm, headers=headers, timeout=10)
        print(f"{sm} -> status {r.status_code}, length: {len(r.content)}")
        if r.status_code == 200 and len(r.content) > 100:
            sample = r.text[:500].replace('\n', ' ')
            print(f"   Sample: {sample}")
    except Exception as e:
        print(f"{sm} -> error: {e}")
