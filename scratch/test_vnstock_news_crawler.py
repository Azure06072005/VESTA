"""scratch/test_vnstock_news_crawler.py
Kiểm tra khả năng cào full body của vnstock_news.Crawler trên các trang báo tài chính.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
from vnstock_news import Crawler

print("=" * 80)
print("THỬ CÀO BÀI VIẾT QUA vnstock_news.Crawler(site_name='cafef'):")
try:
    c = Crawler(site_name="cafef", use_predefined_config=True)
    articles = c.get_latest_articles()
    print(f"Lấy được {len(articles)} bài từ CafeF:")
    if articles:
        first_art = articles[0]
        print("Chi tiết bài đầu tiên:")
        for k, v in first_art.items():
            str_v = str(v)
            if len(str_v) > 150:
                str_v = str_v[:150] + "... [TRUNCATED]"
            print(f"  {k}: {str_v}")
        
        # Nếu có link, thử lấy full details
        link = first_art.get('link') or first_art.get('url')
        if link:
            print(f"\nThử cào nội dung chi tiết bài viết (get_article_details) từ {link}:")
            details = c.get_article_details(link)
            print("Kết quả get_article_details:")
            for k, v in (details or {}).items():
                str_v = str(v)
                if len(str_v) > 200:
                    str_v = str_v[:200] + "... [TRUNCATED]"
                print(f"  {k}: {str_v}")
except Exception as e:
    print("Lỗi:", e)
