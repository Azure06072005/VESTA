import sys
import urllib.request
import ssl
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

sources_to_test = [
    # Group D: Industry Associations
    ("vafie", "VAFIE ĐTNN", "https://vafie.org.vn/sitemap.xml", "xml_sitemap"),
    ("viea", "VEIA Điện tử", "https://veia.org.vn/wp-sitemap-posts-post-1.xml", "xml_sitemap"),
    ("hhbvt", "HH BV Tư nhân", "https://hiephoibenhvientu.com.vn/wp-sitemap-posts-post-1.xml", "xml_sitemap"),
    ("vpsaspice", "VPSA Hồ tiêu", "https://vpsaspice.org/post-sitemap.xml", "xml_sitemap"),
    ("avnuc", "AVNUC Năng lượng", "https://avnuc.vn/post-sitemap.xml", "xml_sitemap"),
    ("huba", "HUBA Doanh nghiệp HCM", "https://huba.vn/post-sitemap1.xml", "xml_sitemap"),
    ("vinasme", "VINASME DNNVV", "https://vinasme.vn/sitemap.xml", "xml_sitemap"),
    ("vacod", "VACOD Hàng tiêu dùng", "https://vacod.vn/sitemap.xml", "xml_sitemap"),
    ("vusta", "VUSTA KH&KT", "https://vusta.vn/sitemap.xml", "xml_sitemap"),
    ("via", "VIA Internet VN", "https://via.org.vn/sitemap.xml", "xml_sitemap"),

    # Group E: Macro Regulatory
    ("hnx_vn", "Sở GDCK Hà Nội", "https://hnx.vn/rss", "rss"),
    
    # Group F: Financial Media Portals
    ("tuoitre", "Báo Tuổi Trẻ", "https://tuoitre.vn/rss/kinh-doanh.rss", "rss"),
    ("vnanet", "Thông tấn xã VN", "https://vnanet.vn/sitemap.xml", "xml_sitemap"),
]

for src_id, name, url, feed_type in sources_to_test:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            content = resp.read()
            soup = BeautifulSoup(content, "html.parser")
            if feed_type == "xml_sitemap":
                locs = [l.get_text(strip=True) for l in soup.find_all("loc")]
                # filter out non-article pages if possible
                article_locs = [l for l in locs if len(l) > 28 and not l.endswith('.xml')]
                print(f"[{src_id:10s}] OK (locs: {len(locs)}, articles: {len(article_locs)}) | Sample: {article_locs[0] if article_locs else 'None'}")
            elif feed_type == "rss":
                items = soup.find_all("item")
                titles = [it.find("title").get_text(strip=True) for it in items if it.find("title")]
                print(f"[{src_id:10s}] OK (items: {len(items)}) | Sample: {titles[0] if titles else 'None'}")
    except Exception as e:
        print(f"[{src_id:10s}] REJECTED/FAILED: {e}")
