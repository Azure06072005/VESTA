import sys
import pathlib
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path("src").resolve()))
from crawlers.cafef_article_body import fetch_article_html
from bs4 import BeautifulSoup

url = "https://cafef.vn/du-lieu/FPT-2977145/fpt-2192026-ngay-gdkhq-thuong-cp-ty-le-101.chn"
html = fetch_article_html(url)
soup = BeautifulSoup(html, "html.parser")

print("Checking potential body containers for /du-lieu/ pages:")
candidates = [
    ("div.detail-content", soup.find("div", class_="detail-content")),
    ("div.contentdetail", soup.find("div", class_="contentdetail")),
    ("div.content_detail", soup.find("div", class_="content_detail")),
    ("div.content", soup.find("div", class_="content")),
    ("div.news_content", soup.find("div", class_="news_content")),
    ("div#content", soup.find(id="content")),
    ("div#newscontent", soup.find(id="newscontent")),
    ("div.box_detail", soup.find("div", class_="box_detail")),
    ("div.box-detail-content", soup.find("div", class_="box-detail-content")),
]

for name, elem in candidates:
    if elem:
        text = elem.get_text(" ", strip=True)
        print(f" -> Found {name}: length = {len(text)} chars | Preview: {repr(text[:120])}")

# Also check div containing paragraphs
for div in soup.find_all("div"):
    ps = div.find_all("p")
    if len(ps) >= 3:
        cls = div.get("class", [])
        id_ = div.get("id", "")
        txt = div.get_text(" ", strip=True)
        print(f" -> Found container with {len(ps)} <p> tags: class={cls}, id={id_}, len={len(txt)}")
        break
