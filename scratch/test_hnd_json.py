import requests
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json; charset=utf-8",
})

api_url = "http://www.hoinongdan.org.vn/DesktopModule/UIArticleInMenu/ArticleInMenuPagination.aspx/LoadArticle"
payload = {
    "article_category_id": 54442,
    "site_id": 4,
    "page": 2,
    "page_size": 15,
    "keyword": "",
    "date_begin": "",
    "date_end": "",
    "show_no": "False",
    "show_post_date": "False",
    "num_of_text": 200,
    "show_view_count": "True",
    "filter_order_in_list": "True",
    "is_default": "False",
    "new": "False",
    "number_of_day": 3,
    "no": -15,
    "articlelang": "vi-VN",
}

resp = s.post(api_url, json=payload, timeout=15)
print(f"JSON API status: {resp.status_code}, len: {len(resp.text)}")
if len(resp.text) > 0:
    print(resp.text[:300])
