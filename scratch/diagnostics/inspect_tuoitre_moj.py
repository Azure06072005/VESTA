import urllib.request
import ssl
from bs4 import BeautifulSoup

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36'}

def fetch(url):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
        return r.read().decode('utf-8', errors='ignore')

print("--- TUOI TRE ---")
try:
    rss = fetch("https://tuoitre.vn/rss/kinh-doanh.rss")
    soup = BeautifulSoup(rss, 'html.parser')
    items = soup.find_all('item')
    print("Tuoitre Kinh doanh items:", len(items))
    if items:
        print("Tuoitre sample title:", items[0].find('title').get_text(strip=True))
        print("Tuoitre sample link:", items[0].find('link').get_text(strip=True) or items[0].find('guid').get_text(strip=True))
        print("Tuoitre sample pubDate:", items[0].find('pubdate').get_text(strip=True))
except Exception as e:
    print("Tuoitre err:", e)

print("--- MOJ (Bo Tu phap) ---")
try:
    sm = fetch("https://moj.gov.vn/sitemap.xml")
    soup = BeautifulSoup(sm, 'html.parser')
    locs = [l.get_text(strip=True) for l in soup.find_all('loc')]
    print("MOJ locs:", len(locs), locs[:3])
except Exception as e:
    print("MOJ err:", e)

print("--- CHINH PHU (vietnam_gov) ---")
try:
    html = fetch("https://chinhphu.vn/thong-cao-bao-chi")
    soup = BeautifulSoup(html, 'html.parser')
    links = [a.get('href') for a in soup.find_all('a', href=True) if 'thong-cao' in a.get('href', '') or 'nghi-quyet' in a.get('href', '')]
    print("Chinhphu links:", len(links), links[:3])
except Exception as e:
    print("Chinhphu err:", e)
