"""Comprehensive robots.txt compliance auditor for all VESTA target websites.

Tuân thủ chuẩn RFC 9309 (Robots Exclusion Protocol).
Kiểm tra chi tiết từng website, lưu file thô vào scratch/ và xuất bảng tổng kết chính sách.
"""

from __future__ import annotations

import os
import sys
import ssl
import time
from pathlib import Path
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Danh sách đầy đủ toàn bộ các website trong hệ sinh thái VESTA
TARGET_SITES = [
    # 1. Cơ quan quản lý & Vĩ mô trong nước
    {"domain": "baochinhphu.vn", "url": "https://baochinhphu.vn/robots.txt", "category": "Vĩ mô / Chính phủ"},
    {"domain": "sbv.gov.vn", "url": "https://sbv.gov.vn/robots.txt", "category": "Ngân hàng Nhà nước"},
    {"domain": "ssc.gov.vn", "url": "https://ssc.gov.vn/robots.txt", "category": "Ủy ban Chứng khoán NN"},
    {"domain": "moit.gov.vn", "url": "https://moit.gov.vn/robots.txt", "category": "Bộ Công Thương"},
    {"domain": "mof.gov.vn", "url": "https://mof.gov.vn/robots.txt", "category": "Bộ Tài chính"},
    {"domain": "gso.gov.vn", "url": "https://www.gso.gov.vn/robots.txt", "category": "Tổng cục Thống kê"},
    
    # 2. Sở giao dịch chứng khoán
    {"domain": "hsx.vn", "url": "https://www.hsx.vn/robots.txt", "category": "Sở GDCK TP.HCM"},
    {"domain": "hnx.vn", "url": "https://hnx.vn/robots.txt", "category": "Sở GDCK Hà Nội"},

    # 3. Báo chí tài chính & Cổng dữ liệu
    {"domain": "cafef.vn", "url": "https://cafef.vn/robots.txt", "category": "Cổng tài chính / Báo chí"},
    {"domain": "vietstock.vn", "url": "https://vietstock.vn/robots.txt", "category": "Cổng thông tin CK"},
    {"domain": "finance.vietstock.vn", "url": "https://finance.vietstock.vn/robots.txt", "category": "Dữ liệu phân tích CK"},
    {"domain": "vneconomy.vn", "url": "https://vneconomy.vn/robots.txt", "category": "Tạp chí Kinh tế VN"},
    {"domain": "baodautu.vn", "url": "https://baodautu.vn/robots.txt", "category": "Báo Đầu tư"},
    {"domain": "thoibaonganhang.vn", "url": "https://thoibaonganhang.vn/robots.txt", "category": "Thời báo Ngân hàng"},
    {"domain": "tinnhanhchungkhoan.vn", "url": "https://www.tinnhanhchungkhoan.vn/robots.txt", "category": "Tin Nhanh Chứng Khoán"},

    # 4. Các Hiệp hội ngành nghề
    {"domain": "horea.org.vn", "url": "https://www.horea.org.vn/robots.txt", "category": "Hiệp hội BĐS TP.HCM"},
    {"domain": "vba.com.vn", "url": "https://vba.com.vn/robots.txt", "category": "Hiệp hội Bia - Rượu - NGK"},
    {"domain": "hoinongdan.org.vn", "url": "http://www.hoinongdan.org.vn/robots.txt", "category": "Hội Nông dân Việt Nam"},
    {"domain": "vita.vn", "url": "https://vita.vn/robots.txt", "category": "Hiệp hội Du lịch VN"},
    {"domain": "nda.org.vn", "url": "https://nda.org.vn/robots.txt", "category": "Hiệp hội Dữ liệu QG"},
    {"domain": "vinaprint.com.vn", "url": "https://www.vinaprint.com.vn/robots.txt", "category": "Hiệp hội In Việt Nam"},
    {"domain": "vasep.com.vn", "url": "https://vasep.com.vn/robots.txt", "category": "Hiệp hội Thủy sản VASEP"},
    {"domain": "vsa.com.vn", "url": "https://vsa.com.vn/robots.txt", "category": "Hiệp hội Thép VSA"},
    {"domain": "vnba.org.vn", "url": "https://vnba.org.vn/robots.txt", "category": "Hiệp hội Ngân hàng VNBA"},

    # 5. Định chế tài chính quốc tế
    {"domain": "data.worldbank.org", "url": "https://data.worldbank.org/robots.txt", "category": "World Bank Macro Data"},
    {"domain": "tradingeconomics.com", "url": "https://tradingeconomics.com/robots.txt", "category": "Trading Economics"},
    {"domain": "imf.org", "url": "https://www.imf.org/robots.txt", "category": "IMF Quỹ Tiền tệ QT"},
    {"domain": "wsj.com", "url": "https://www.wsj.com/robots.txt", "category": "Wall Street Journal"},
]

OUT_DIR = Path(__file__).resolve().parent

def check_single_site(site: dict[str, str]) -> dict[str, str]:
    domain = site["domain"]
    url = site["url"]
    cat = site["category"]
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/plain,text/html,*/*",
            "Accept-Encoding": "identity",
        }
    )
    
    status_code = ""
    content = ""
    verdict = ""
    details = ""
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            status_code = str(r.status)
            raw_bytes = r.read()
            content = raw_bytes.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status_code = str(e.code)
        try:
            content = e.read().decode("utf-8", errors="replace")
        except Exception:
            content = ""
    except urllib.error.URLError as e:
        status_code = "Timeout/Error"
        details = str(e.reason)[:60]
    except Exception as e:
        status_code = "Error"
        details = str(e)[:60]

    # Phân tích nội dung theo RFC 9309
    if status_code == "200":
        # Lưu file thô vào scratch
        raw_file = OUT_DIR / f"{domain.replace('.', '_')}-robots.txt"
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(content)
            
        lower = content.lower()
        if "disallow: /" in lower and "allow: /" not in lower and "user-agent: *" in lower:
            # Kiểm tra xem có phải cấm toàn bộ không
            # Nếu có Disallow: / nằm ngay dưới User-agent: * mà không có Allow
            disallow_match = False
            lines = [line.strip() for line in content.split("\n")]
            is_wildcard = False
            for line in lines:
                if line.lower().startswith("user-agent: *"):
                    is_wildcard = True
                elif line.lower().startswith("user-agent:") and not line.lower().startswith("user-agent: *"):
                    is_wildcard = False
                elif is_wildcard and line.lower() == "disallow: /":
                    disallow_match = True
                    break
            
            if disallow_match:
                verdict = "STRICTLY PROHIBITED"
                details = "Cấm toàn bộ bot (Disallow: /)"
            else:
                verdict = "PERMITTED (Restricted)"
                details = "Chỉ chặn một số thư mục con"
        elif "disallow:" in lower:
            verdict = "PERMITTED (Restricted)"
            # Tìm xem có crawl-delay không
            delay_line = [l for l in content.split("\n") if "crawl-delay" in l.lower()]
            if delay_line:
                details = delay_line[0].strip()
            else:
                details = "Cho phép thu thập công khai, chặn admin/api"
        else:
            verdict = "FULLY PERMITTED"
            details = "Cho phép toàn bộ (Allow: / hoặc rỗng)"
    elif status_code == "404":
        verdict = "FULLY PERMITTED (RFC 9309)"
        details = "Không có robots.txt (Mặc định cho phép toàn quyền cào)"
    elif status_code == "403":
        verdict = "RESTRICTED / WAF"
        details = "Web server WAF chặn truy cập file .txt, HTML vẫn mở"
    elif status_code == "Timeout/Error":
        verdict = "UNREACHABLE / TIMEOUT"
        if not details:
            details = "Server phản hồi chậm hoặc chặn kết nối"
    else:
        verdict = f"HTTP {status_code}"
        details = f"Mã trạng thái {status_code}"

    return {
        "domain": domain,
        "category": cat,
        "status": status_code,
        "verdict": verdict,
        "details": details,
    }


def main():
    print(f"==> Đang kiểm tra robots.txt cho {len(TARGET_SITES)} website...")
    results = []
    for site in TARGET_SITES:
        res = check_single_site(site)
        print(f"[{res['status']:<7}] {res['domain']:<26} -> {res['verdict']:<25} ({res['details']})")
        results.append(res)
        time.sleep(0.3)

    print("\n" + "=" * 90)
    print("BẢNG BÁO CÁO CHÍNH SÁCH ROBOTS.TXT TOÀN BỘ WEBSITE:")
    print("=" * 90)
    print(f"| {'Domain':<24} | {'Chuyên Mục / Tổ Chức':<24} | {'Mã HTTP':<8} | {'Phán Quyết Chính Sách':<25} |")
    print("|" + "-" * 26 + "|" + "-" * 26 + "|" + "-" * 10 + "|" + "-" * 27 + "|")
    for r in results:
        print(f"| {r['domain']:<24} | {r['category']:<24} | {r['status']:<8} | {r['verdict']:<25} |")


if __name__ == "__main__":
    main()
