import urllib.request
import urllib.parse
import sys
import re
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Referer': 'https://cafef.vn/du-lieu/lich-su-kien.chn'
}

# 1. GET page to extract ViewState
url = 'https://cafef.vn/du-lieu/lich-su-kien.chn'
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as res:
    html = res.read().decode('utf-8', errors='ignore')

soup = BeautifulSoup(html, 'html.parser')
viewstate = soup.find('input', id='__VIEWSTATE').get('value', '')
eventvalidation = soup.find('input', id='__EVENTVALIDATION').get('value', '') if soup.find('input', id='__EVENTVALIDATION') else ''
generator = soup.find('input', id='__VIEWSTATEGENERATOR').get('value', '') if soup.find('input', id='__VIEWSTATEGENERATOR') else ''

print(f"ViewState length: {len(viewstate)}")

# 2. POST to search for symbol FPT
form_data = {
    '__VIEWSTATE': viewstate,
    '__VIEWSTATEGENERATOR': generator,
    '__EVENTVALIDATION': eventvalidation,
    'ctl00$ContentPlaceHolder1$LichSuKien2$txtKeyword': 'FPT',
    'ctl00$ContentPlaceHolder1$LichSuKien2$dlType': '0',
    'ctl00$ContentPlaceHolder1$LichSuKien2$dpkTradeDate1$txtDatePicker': '01/01/2010',
    'ctl00$ContentPlaceHolder1$LichSuKien2$dpkTradeDate2$txtDatePicker': '31/12/2026',
    'ctl00$ContentPlaceHolder1$LichSuKien2$btSearch.x': '10',
    'ctl00$ContentPlaceHolder1$LichSuKien2$btSearch.y': '10',
    'ctl00$ContentPlaceHolder1$LichSuKien2$hdfStatus': '1'
}

encoded_data = urllib.parse.urlencode(form_data).encode('utf-8')
post_req = urllib.request.Request(url, data=encoded_data, headers=headers)
with urllib.request.urlopen(post_req, timeout=12) as res:
    post_html = res.read().decode('utf-8', errors='ignore')

post_soup = BeautifulSoup(post_html, 'html.parser')

# Find table with event rows
tables = post_soup.find_all('table')
for i, t in enumerate(tables):
    rows = t.find_all('tr')
    if len(rows) > 3:
        headers_row = [th.get_text(strip=True) for th in rows[0].find_all(['th', 'td'])]
        if any('khônghưởng quyền' in h or 'không hưởng quyền' in h or 'Sự kiện' in h for h in headers_row):
            print(f"Found Target Event Table ({len(rows)} rows):", headers_row)
            for r in rows[1:10]:
                tds = [td.get_text(strip=True) for td in r.find_all('td')]
                if len(tds) >= 6:
                    print("  Row:", tds[:6])
