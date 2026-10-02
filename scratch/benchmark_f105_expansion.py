import duckdb
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con_news = duckdb.connect("db/vesta_news.duckdb", read_only=True)
# Lấy mẫu 1,000 bài từ tinnhanhchungkhoan có body
sample_articles = con_news.execute("""
    SELECT n.source_url, n.headline, r.body
    FROM core.news n
    JOIN core.news_resources r ON n.source_url = r.source_url
    WHERE n.source = 'tinnhanhchungkhoan'
      AND r.body IS NOT NULL AND length(trim(r.body)) > 100
    LIMIT 1000;
""").fetchall()
con_news.close()

print(f"Đã tải {len(sample_articles)} bài báo mẫu từ tinnhanhchungkhoan.")

# 1. Thử nghiệm với Matcher hiện tại (Baseline F105)
sys.path.insert(0, "src")
from pipeline.news_fundamental_entity_matcher import FundamentalEntityRegistry

t0 = time.time()
base_reg = FundamentalEntityRegistry()
base_reg.load_registry()

base_matched_urls = set()
base_match_count = 0
for url, headline, body in sample_articles:
    res = base_reg.match_entities_in_text(headline, body, url)
    if res:
        base_matched_urls.add(url)
        base_match_count += len(res)

t_base = time.time() - t0
print(f"\n[BASELINE F105]:")
print(f"  - Thời gian xử lý: {t_base:.2f}s ({len(sample_articles)/t_base:.1f} articles/s)")
print(f"  - Số bài phục hồi được mã: {len(base_matched_urls)} / {len(sample_articles)} ({len(base_matched_urls)/len(sample_articles)*100:.2f}%)")
print(f"  - Tổng số thực thể khớp: {base_match_count}")

# 2. Thử nghiệm mở rộng: Thêm Brand Names (en_organ_name như Vietcombank, Vinamilk, Techcombank, FPT...)
# Lấy danh sách thương hiệu từ dim_symbol
con_snap = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
df_sym = con_snap.execute("SELECT symbol, organ_name, en_organ_name FROM core.dim_symbol").df()
con_snap.close()

brand_dict = {}
BRAND_BLACKLIST = {"VIETNAM", "VIET NAM", "HOLDINGS", "GROUP", "INVESTMENT", "COMPANY", "CORP", "BANK"}

for _, row in df_sym.iterrows():
    sym = row['symbol'].strip().upper()
    en = str(row['en_organ_name']).strip()
    if en and len(en) >= 3 and en.upper() not in BRAND_BLACKLIST:
        brand_dict[en.lower()] = sym

print(f"\nĐã tổng hợp {len(brand_dict)} thương hiệu quốc tế/thương mại (Vietcombank, Vinamilk, Techcombank, FPT Corp...).")

t1 = time.time()
ext_matched_urls = set(base_matched_urls)
extra_matches = 0

for url, headline, body in sample_articles:
    full_text = f" {headline.lower()} {body[:2000].lower()} "
    for brand, sym in brand_dict.items():
        if f" {brand} " in full_text:
            ext_matched_urls.add(url)
            extra_matches += 1

t_ext = time.time() - t1
print(f"\n[EXPANDED F105 (+ BRAND NAMES)]:")
print(f"  - Thời gian bổ sung: {t_ext:.2f}s")
print(f"  - Số bài phục hồi được mã: {len(ext_matched_urls)} / {len(sample_articles)} ({len(ext_matched_urls)/len(sample_articles)*100:.2f}%)")
print(f"  - Số lượng bài phục hồi tăng thêm: +{len(ext_matched_urls) - len(base_matched_urls)} bài (+{(len(ext_matched_urls) - len(base_matched_urls))/len(sample_articles)*100:.2f}%)")
