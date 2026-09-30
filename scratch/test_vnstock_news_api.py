"""scratch/test_vnstock_news_api.py
Khám phá thư viện vnstock_news và kiểm tra nội dung bài viết (body/content).
"""
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

import vnstock_news
from vnstock_news import list_supported_sites, Crawler, EnhancedNewsCrawler

print("=" * 80)
print("1. DANH SÁCH CÁC TRANG TIN HỖ TRỢ TRONG vnstock_news:")
sites = list_supported_sites()
print(f"Tổng số trang hỗ trợ: {len(sites)}")
print("Danh sách:", sites)

print("\n" + "=" * 80)
print("2. THỬ NGHIỆM CÀO BẰNG vnstock_news.Crawler(site_name='cafef'):")
try:
    crawler = Crawler(site_name="cafef", use_predefined_config=True)
    print("Methods của Crawler:", [m for m in dir(crawler) if not m.startswith('_')])
    # Thử lấy danh sách bài viết gần nhất
    if hasattr(crawler, "crawl"):
        print("Đang crawl thử 1 trang bằng crawler.crawl()...")
        res_crawl = crawler.crawl(max_pages=1) if "max_pages" in crawler.crawl.__code__.co_varnames else crawler.crawl()
        print(f"Kết quả crawl type: {type(res_crawl)}")
        if isinstance(res_crawl, list):
            print(f"Số lượng bài: {len(res_crawl)}")
            if len(res_crawl) > 0:
                print("Mẫu bài 1:", res_crawl[0])
except Exception as e:
    print("Lỗi khi chạy Crawler:", e)

# 3. Thử nghiệm cào qua vnstock_data / Company.news() (Module được dùng trong F003 gốc)
print("\n" + "=" * 80)
print("3. THỬ NGHIỆM CÀO QUA F003 GỐC (Company.news()):")
try:
    from vnstock.api.company import Company
    comp = Company(symbol="FPT", source="VCI")
    df_news = comp.news()
    print("FPT Company.news() shape:", df_news.shape)
    print("Cột:", list(df_news.columns))
    print("\nKiểm tra 3 dòng đầu:")
    for i, r in df_news.head(3).iterrows():
        print(f"--- Tin {i+1} ---")
        for col in df_news.columns:
            val = str(r[col])
            if len(val) > 100:
                val = val[:100] + "... [TRUNCATED]"
            print(f"  {col}: {val}")
except Exception as e:
    print("Lỗi Company.news():", e)

# 4. Thử nghiệm EnhancedNewsCrawler
print("\n" + "=" * 80)
print("4. THỬ NGHIỆM EnhancedNewsCrawler:")
try:
    enc = EnhancedNewsCrawler()
    print("EnhancedNewsCrawler methods:", [m for m in dir(enc) if not m.startswith('_')])
    if hasattr(enc, "crawl"):
        print("Thử gọi enc.crawl()...")
except Exception as e:
    print("Lỗi EnhancedNewsCrawler:", e)
