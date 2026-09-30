import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

crawler_files = (
    glob.glob('src/crawlers/*crawler*.py') + 
    glob.glob('src/crawlers/*news*.py') +
    glob.glob('src/crawlers/sbv*.py') +
    glob.glob('src/crawlers/ssc*.py') +
    glob.glob('src/crawlers/vneconomy*.py') +
    glob.glob('src/crawlers/cafef*.py')
)
crawler_files = sorted(list(set(crawler_files)))

print("="*90)
print("RÀ SOÁT CƠ CHẾ BẢO VỆ WAF, 403 FORBIDDEN, CLOUDFLARE & ANTI-BOT TRONG MÃ NGUỒN CRAWLERS")
print("="*90)

keywords = ['403', 'forbidden', 'waf', 'cloudflare', 'captcha', 'rate_limit', '429']

for f in crawler_files:
    fname = os.path.basename(f)
    try:
        with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
            lines = fp.readlines()
        
        matched_lines = []
        for line_no, line in enumerate(lines, 1):
            for kw in keywords:
                if re.search(r'\b' + kw + r'\b', line, re.IGNORECASE):
                    matched_lines.append((line_no, kw, line.strip()))
                    break
        
        if matched_lines:
            print(f"\n[!] CRAWLER: {fname}")
            for lno, kw, text in matched_lines[:4]:
                print(f"    Line {lno:4d} [{kw}]: {text[:85]}")
    except Exception as e:
        print(f"Lỗi đọc {fname}: {e}")
