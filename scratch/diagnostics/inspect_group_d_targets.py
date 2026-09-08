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

# 1. vafie
print("--- VAFIE ---")
try:
    sitemap = fetch("https://vafie.org.vn/sitemap.xml")
    soup = BeautifulSoup(sitemap, 'html.parser')
    locs = [l.get_text(strip=True) for l in soup.find_all('loc') if '.html' in l.get_text()]
    print("VAFIE locs:", len(locs), locs[:2])
    if locs:
        art = fetch(locs[0])
        asoup = BeautifulSoup(art, 'html.parser')
        h1 = asoup.find('h1')
        print("VAFIE title:", h1.get_text(strip=True) if h1 else 'None')
except Exception as e:
    print("VAFIE err:", e)

# 2. huba
print("--- HUBA ---")
try:
    blog = fetch("https://huba.vn/blogs/tin-tuc-huba")
    soup = BeautifulSoup(blog, 'html.parser')
    art_links = [a.get('href') for a in soup.find_all('a', href=True) if '/blogs/tin-tuc-huba/' in a.get('href')]
    print("HUBA links:", len(art_links), art_links[:3])
    if art_links:
        full_u = "https://huba.vn" + art_links[0] if art_links[0].startswith('/') else art_links[0]
        art = fetch(full_u)
        asoup = BeautifulSoup(art, 'html.parser')
        h1 = asoup.find('h1')
        print("HUBA title:", h1.get_text(strip=True) if h1 else 'None')
except Exception as e:
    print("HUBA err:", e)

# 3. vpsaspice
print("--- VPSASPICE ---")
try:
    sm = fetch("https://vpsaspice.org/post-sitemap.xml")
    soup = BeautifulSoup(sm, 'html.parser')
    locs = [l.get_text(strip=True) for l in soup.find_all('loc')]
    print("VPSASPICE locs:", len(locs), locs[:2])
    if locs:
        art = fetch(locs[0])
        asoup = BeautifulSoup(art, 'html.parser')
        h1 = asoup.find('h1')
        print("VPSASPICE title:", h1.get_text(strip=True) if h1 else 'None')
except Exception as e:
    print("VPSASPICE err:", e)

# 4. viea
print("--- VIEA ---")
try:
    sm = fetch("https://veia.org.vn/wp-sitemap-posts-post-1.xml")
    soup = BeautifulSoup(sm, 'html.parser')
    locs = [l.get_text(strip=True) for l in soup.find_all('loc')]
    print("VIEA locs:", len(locs), locs[:2])
    if locs:
        art = fetch(locs[0])
        asoup = BeautifulSoup(art, 'html.parser')
        h1 = asoup.find('h1')
        print("VIEA title:", h1.get_text(strip=True) if h1 else 'None')
except Exception as e:
    print("VIEA err:", e)

# 5. vacod
print("--- VACOD ---")
try:
    html = fetch("https://vacod.vn/cms/public-hashtag/view?id=2066&title=tin-tuc-hiep-hoi-2066")
    soup = BeautifulSoup(html, 'html.parser')
    links = [a.get('href') for a in soup.find_all('a', href=True) if '/view?id=' in a.get('href', '') or 'tin-tuc' in a.get('href', '')]
    print("VACOD links:", len(links), links[:3])
except Exception as e:
    print("VACOD err:", e)
