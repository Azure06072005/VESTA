import duckdb
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, "src")
from pipeline.news_fundamental_entity_matcher import FinancialRelevanceClassifier, FundamentalEntityRegistry

con_news = duckdb.connect("db/vesta_news.duckdb", read_only=True)
sample_tuoitre = con_news.execute("""
    SELECT n.source_url, n.headline, r.body
    FROM core.news n
    JOIN core.news_resources r ON n.source_url = r.source_url
    WHERE n.source = 'tuoitre'
      AND r.body IS NOT NULL AND length(trim(r.body)) > 100
    LIMIT 1000;
""").fetchall()
con_news.close()

print(f"Đã tải {len(sample_tuoitre)} bài báo mẫu từ tuoitre.")

classifier = FinancialRelevanceClassifier()
reg = FundamentalEntityRegistry()
reg.load_registry()

cat_counts = {}
matched_ticker_count = 0
noise_count = 0

for url, headline, body in sample_tuoitre:
    matches = reg.match_entities_in_text(headline, body, url)
    has_entity = len(matches) > 0
    if has_entity:
        matched_ticker_count += 1
    
    cat, is_rel, score = classifier.classify_article(headline, body, has_matched_entity=has_entity)
    cat_counts[cat] = cat_counts.get(cat, 0) + 1
    if cat == "IRRELEVANT_NOISE":
        noise_count += 1

print("\n[KẾT QUẢ KHẢO SÁT TUỔI TRẺ (1,000 bài)]:")
print(f"  - Số bài nhận diện được thực thể chứng khoán: {matched_ticker_count} ({matched_ticker_count/len(sample_tuoitre)*100:.2f}%)")
print(f"  - Phân bổ chuyên mục (Relevance Gate):")
for cat, cnt in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"    * {cat:20s}: {cnt:4d} bài ({cnt/len(sample_tuoitre)*100:.2f}%)")
