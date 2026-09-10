import sys
sys.path.insert(0, 'd:/VESTA')
import requests
from bs4 import BeautifulSoup
import duckdb
import pandas as pd
from src.crawlers.thoibaotaichinh_crawler import parse_tbtc_listing, parse_tbtc_article, write_macro_policy

r = requests.get('https://thoibaotaichinhvietnam.vn/tai-chinh', headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
articles = parse_tbtc_listing(r.text)
print('Articles count:', len(articles))

records = []
for a in articles[:2]:
    art_r = requests.get(a['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    rec = parse_tbtc_article(art_r.text, a['url'], fallback_title=a['title'])
    if rec:
        records.append(rec)

print('Parsed records:', len(records))
con = duckdb.connect('d:/VESTA/db/vesta.duckdb', read_only=False)
df = pd.DataFrame(records)
n = write_macro_policy(con, df)
print('Written to DuckDB:', n)
con.close()
