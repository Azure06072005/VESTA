import urllib.request
import urllib.error
import ssl
from bs4 import BeautifulSoup

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

group_d_targets = [
    ("huba", "https://huba.vn/blogs/tin-tuc-huba"),
    ("vacod", "https://vacod.vn/tin-tuc-su-kien/"),
    ("vpsaspice", "https://vpsaspice.org/sitemap_index.xml"),
    ("viea", "https://veia.org.vn/wp-sitemap.xml"),
    ("avnuc", "https://avnuc.vn/sitemap_index.xml"),
    ("via", "https://via.org.vn/tin-tuc"),
    ("hhbvt", "https://hiephoibenhvientu.com.vn/wp-sitemap.xml"),
    ("vinasme", "https://vinasme.vn/tin-tuc/"),
    ("vafie_org", "https://vafie.org.vn/sitemap.xml"),
    ("vusta", "https://vusta.vn/tin-tuc-su-kien-c37.html"),
]

for name, url in group_d_targets:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            content = resp.read()
            print(f"[{name:10s}] HTTP {resp.getcode()} | size: {len(content)} bytes | url: {url}")
            if b"sitemap" in content.lower() or b"urlset" in content.lower():
                soup = BeautifulSoup(content, "html.parser")
                locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
                print(f"   -> Found {len(locs)} loc entries. Sample: {locs[:2]}")
            else:
                soup = BeautifulSoup(content, "html.parser")
                links = [a.get("href") for a in soup.find_all("a", href=True) if len(a.get("href")) > 10]
                print(f"   -> HTML page. Found {len(links)} links. Sample: {links[:3]}")
    except Exception as e:
        print(f"[{name:10s}] FAILED: {e}")
