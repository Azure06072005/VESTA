import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb
import re

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)

# Let's inspect 10 headlines and body snippets from Tuổi Trẻ and Tiền Phong that are non-financial (lifestyle/noise)
# vs financial
print("=== TESTING NOISE DETECTION ON TUOI TRE & TIEN PHONG ===")

noise_patterns = [
    r"\b(showbiz|hoa hậu|người mẫu|ca sĩ|diễn viên|nghệ sĩ|scandal|hẹn hò|ly hôn|tiểu tam|ngoại tình)\b",
    r"\b(tai nạn|va chạm giao thông|tử vong|chết đuối|án mạng|giết người|ma túy|bắt tạm giam|khởi tố bị can|trộm cắp|cướp giật)\b",
    r"\b(bóng đá|ngoại hạng anh|world cup|v-league|u23|đội tuyển quốc gia|bàn thắng|huấn luyện viên)\b",
    r"\b(làm đẹp|chăm sóc da|thực đơn|món ăn|ngộ độc|bệnh viện|ung thư|giảm cân|tập gym|du lịch phượt)\b",
]

finance_patterns = [
    r"\b(chứng khoán|cổ phiếu|cổ tức|lợi nhuận|doanh thu|lãi ròng|báo cáo tài chính|thua lỗ|tăng trưởng|hđqt|đại hội cổ đông)\b",
    r"\b(ngân hàng|lãi suất|tín dụng|nợ xấu|tỷ giá|ngoại tệ|dự trữ ngoại hối|sbv|nhnn|trái phiếu|room tín dụng)\b",
    r"\b(kinh tế|gdp|cpi|lạm phát|fdi|xuất khẩu|nhập khẩu|thương mại|vốn đầu tư|giải ngân đầu tư công|chính sách tiền tệ)\b",
    r"\b(bất động sản|dự án|khu công nghiệp|thị trường|doanh nghiệp|tập đoàn|thương vụ|thâu tóm|sáp nhập|ipo)\b",
]

combined_noise_regex = re.compile("|".join(noise_patterns), re.IGNORECASE)
combined_finance_regex = re.compile("|".join(finance_patterns), re.IGNORECASE)

# Query 1,000 articles from Tuổi Trẻ and Tiền Phong
sample_df = con.execute("""
    SELECT source, headline, substr(body, 1, 1000) as body_sample
    FROM core.news
    WHERE source IN ('tuoitre', 'tienphong') AND body IS NOT NULL AND length(body) > 100
    LIMIT 2000
""").df()

noise_only = 0
finance_only = 0
both = 0
neither = 0

samples_noise = []
samples_finance = []

for _, row in sample_df.iterrows():
    text = (row['headline'] or '') + " " + (row['body_sample'] or '')
    has_noise = bool(combined_noise_regex.search(text))
    has_finance = bool(combined_finance_regex.search(text))
    
    if has_noise and not has_finance:
        noise_only += 1
        if len(samples_noise) < 5:
            samples_noise.append((row['source'], row['headline']))
    elif has_finance and not has_noise:
        finance_only += 1
        if len(samples_finance) < 5:
            samples_finance.append((row['source'], row['headline']))
    elif has_noise and has_finance:
        both += 1
    else:
        neither += 1

total = len(sample_df)
print(f"Total sampled: {total}")
print(f"Pure Noise (Lifestyle/Crime/Sports/Health): {noise_only} ({noise_only/total*100:.1f}%)")
print(f"Pure Finance/Economy: {finance_only} ({finance_only/total*100:.1f}%)")
print(f"Mixed (Has both financial and noise keywords): {both} ({both/total*100:.1f}%)")
print(f"Neither (Unclassified general): {neither} ({neither/total*100:.1f}%)")

print("\n--- Pure Noise Samples ---")
for s, h in samples_noise:
    print(f"[{s}] {h}")

print("\n--- Pure Finance Samples ---")
for s, h in samples_finance:
    print(f"[{s}] {h}")

con.close()
