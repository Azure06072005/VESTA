import urllib.request
import re
import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

url = 'https://cafef.vn/du-lieu/lich-su-kien.chn'
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as res:
    html = res.read().decode('utf-8', errors='ignore')

soup = BeautifulSoup(html, 'html.parser')

forms = soup.find_all('form')
print(f"Total forms: {len(forms)}")
for i, f in enumerate(forms):
    print(f"Form {i}: action={f.get('action')}, method={f.get('method')}, id={f.get('id')}")
    inputs = f.find_all(['input', 'select', 'button'])
    input_names = [(inp.get('name'), inp.get('id'), inp.get('type'), inp.get('value')) for inp in inputs]
    print(f"  Inputs count: {len(inputs)}")
    for name, iid, itype, ival in input_names[:15]:
        print(f"    name={name}, id={iid}, type={itype}, value={ival}")

# Check for pagination links or buttons
paging = soup.find_all(class_=re.compile(r'pag|nav|paging', re.I))
print(f"\nPaging elements: {len(paging)}")
for p in paging:
    print("  Paging tag:", p.name, p.get('class'), [a.get('href') for a in p.find_all('a')])

# Check table 2 rows in detail
table2 = soup.find_all('table')[2]
rows = table2.find_all('tr')
print(f"\nTable 2 has {len(rows)} rows. Displaying first 5 rows:")
for r in rows[1:6]:
    cells = [c.get_text(strip=True) for c in r.find_all(['td', 'th'])]
    print("  Row:", cells[:6])
