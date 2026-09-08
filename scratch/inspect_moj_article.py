import urllib.request
import ssl
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0'}

url_moj = 'https://moj.gov.vn/portal/tin-tuc/chi-tiet/thu-chuc-mung-cua-bo-truong-bo-tu-phap-nhan-dip-ky-niem-29-nam-ngay-thanh-lap-he-thong-tro-giup-phap-ly-tkrmqged24.html'
req = urllib.request.Request(url_moj, headers=headers)
with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
    soup = BeautifulSoup(resp.read(), 'html.parser')
    for tag in ['h1', 'h2', 'h3']:
        for h in soup.find_all(tag):
            print(f"{tag}: {h.get_text().strip()[:60]}")
    
    # Check all divs with text > 200 chars
    large_divs = [d for d in soup.find_all('div') if len(d.get_text(strip=True)) > 200]
    print(f"Total divs with text > 200: {len(large_divs)}")
    for d in large_divs[:3]:
        print("Div class:", d.get('class'), "id:", d.get('id'), "len:", len(d.get_text(strip=True)))
