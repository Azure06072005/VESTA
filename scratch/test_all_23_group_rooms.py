import requests
import json
import time
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# 23 chỉ số trong ảnh của người dùng
all_group_rooms = [
    # Cột 1 trong ảnh
    ('VNXALLSHARE', 'VNXALL'), 
    ('VN100', 'VN100'),
    ('VNDIAMOND', 'VNDIAMOND'),
    ('VNFINSELECT', 'VNFINSELECT'),
    ('VNFINLEAD', 'VNFINLEAD'),
    ('VN30', 'VN30'),
    ('VNFINANCIALS', 'VNFIN'),
    ('VNMATERIALS', 'VNMAT'),
    ('VNINDUSTRIALS', 'VNIND'),
    ('VNCONSUMER STAPLES', 'VNCONS'),
    ('VNCONSUMER DISC', 'VNCOND'),
    ('VNHEALTH CARE', 'VNHEAL'),
    # Cột 2 trong ảnh
    ('VNMIDCAP', 'VNMID'),
    ('VNSMALLCAP', 'VNSML'),
    ('VNENERGY', 'VNENE'),
    ('VNREAL ESTATE', 'VNREAL'),
    ('VNTECHNOLOGY', 'VNIT'),
    ('VNUTILITIES', 'VNUTI'),
    ('VNSI', 'VNSI'),
    ('VNALLSHARE', 'VNALL'),
    ('VNX50', 'VNX50'),
    ('VNMITECH', 'VNMITECH'),
    ('VN50GROWTH', 'VN50GROWTH'),
    ('VNDIVIDEND', 'VNDIVIDEND')
]

now_ts = int(time.time())
from_ts = int(time.mktime(time.strptime("2015-01-01", "%Y-%m-%d")))

vnd_base = "https://dchart-api.vndirect.com.vn/dchart/history"

print(f"{'Tên hiển thị':22} | {'Mã symbol':12} | {'Trạng thái':10} | {'Số phiên':10} | {'Từ ngày':12} | {'Đến ngày':12}")
print("-" * 90)

successful_crawled = {}

for display_name, sym in all_group_rooms:
    # Thử cả mã gốc và mã rút gọn nếu cần
    for candidate_code in [sym, display_name.replace(" ", "")]:
        url = f"{vnd_base}?resolution=D&symbol={candidate_code}&from={from_ts}&to={now_ts}"
        try:
            r = requests.get(url, headers=headers, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if data.get('s') == 'ok' and len(data.get('t', [])) > 0:
                    t_list = data['t']
                    start_dt = time.strftime('%Y-%m-%d', time.localtime(t_list[0]))
                    end_dt = time.strftime('%Y-%m-%d', time.localtime(t_list[-1]))
                    print(f"{display_name:22} | {candidate_code:12} | {'OK':10} | {len(t_list):10,d} | {start_dt:12} | {end_dt:12}")
                    successful_crawled[candidate_code] = data
                    break
        except Exception as e:
            continue
    else:
        print(f"{display_name:22} | {sym:12} | {'NOT FOUND':10} | {'0':10} | {'-':12} | {'-':12}")

print(f"\nTổng kết: Tìm thấy dữ liệu cho {len(successful_crawled)}/{len(all_group_rooms)} rổ nhóm chỉ số!")
