import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb
import re
import unicodedata
import pandas as pd
from typing import Dict, List, Tuple, Set, Optional

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.lower())
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

print("=== PROTOTYPING NEWS CLASSIFICATION & FUNDAMENTAL ENTITY RESOLUTION ===")

# 1. Load entities from snapshot / backup
con_snap = duckdb.connect('db/vesta_backup.duckdb', read_only=True)

# Shareholders (4,268)
df_shareholders = con_snap.execute("""
    SELECT DISTINCT symbol, trim(shareholder_name) as name, ownership_percentage
    FROM core.company_shareholders
    WHERE shareholder_name IS NOT NULL AND length(trim(shareholder_name)) >= 5
""").df()

# Corporate executives & company type (1,522)
df_overview = con_snap.execute("""
    SELECT symbol, trim(ceo_name) as ceo_name, ceo_position, company_type
    FROM core.company_overview
    WHERE ceo_name IS NOT NULL AND length(trim(ceo_name)) >= 5
""").df()

# Company names (1,751)
df_symbols = con_snap.execute("""
    SELECT symbol, organ_name, en_organ_name, industry_name
    FROM core.dim_symbol
""").df()

con_snap.close()

# Build fast keyword lookup dicts
shareholder_map: Dict[str, List[Tuple[str, float]]] = {}
for _, row in df_shareholders.iterrows():
    name = row['name']
    norm = normalize_text(name)
    if len(norm.split()) >= 2 and norm not in ['viet nam', 'tap doan', 'cong ty']:
        shareholder_map.setdefault(norm, []).append((row['symbol'], row['ownership_percentage'] or 0.0))

ceo_map: Dict[str, List[Tuple[str, str, str]]] = {}
for _, row in df_overview.iterrows():
    raw_ceo = row['ceo_name']
    clean_ceo = re.sub(r"^(mr\.|ms\.|mrs\.|ông|bà)\s*", "", raw_ceo, flags=re.IGNORECASE).strip()
    norm = normalize_text(clean_ceo)
    if len(norm.split()) >= 2:
        ceo_map.setdefault(norm, []).append((row['symbol'], row['ceo_position'] or 'Lãnh đạo', row['company_type'] or 'Cổ phần'))

# Regex for Noise (Lifestyle, Crime, Gossip, Sports, Health)
NOISE_REGEX = re.compile(
    r"\b(showbiz|hoa hậu|người mẫu|ca sĩ|diễn viên|nghệ sĩ|scandal|hẹn hò|ly hôn|tiểu tam|ngoại tình|"
    r"tai nạn|va chạm giao thông|tử vong|chết đuối|án mạng|giết người|ma túy|trộm cắp|cướp giật|"
    r"bóng đá|ngoại hạng anh|world cup|v-league|u23|bàn thắng|huấn luyện viên|"
    r"làm đẹp|chăm sóc da|thực đơn|món ăn|ngộ độc|bệnh viện|ung thư|giảm cân)\b",
    re.IGNORECASE
)

# Regex for Financial & Economic Relevance
FINANCE_REGEX = re.compile(
    r"\b(chứng khoán|cổ phiếu|cổ tức|lợi nhuận|doanh thu|lãi ròng|báo cáo tài chính|thua lỗ|tăng trưởng|hđqt|đại hội cổ đông|"
    r"ngân hàng|lãi suất|tín dụng|nợ xấu|tỷ giá|ngoại tệ|sbv|nhnn|trái phiếu|room tín dụng|"
    r"kinh tế|gdp|cpi|lạm phát|fdi|xuất khẩu|nhập khẩu|thương mại|vốn đầu tư|đầu tư công|"
    r"bất động sản|dự án|khu công nghiệp|thương vụ|thâu tóm|sáp nhập|ipo)\b",
    re.IGNORECASE
)

# Connect to news and test on sample 3,000 articles
con_news = duckdb.connect('db/vesta_news.duckdb', read_only=True)
sample_articles = con_news.execute("""
    SELECT source_url, source, symbol, headline, substr(body, 1, 1500) as body_sample
    FROM core.news
    WHERE body IS NOT NULL AND length(body) > 100
    LIMIT 3000
""").df()
con_news.close()

results = []
for _, row in sample_articles.iterrows():
    headline = row['headline'] or ''
    body = row['body_sample'] or ''
    full_text = headline + " " + body
    norm_text = normalize_text(full_text)
    
    # Check noise & finance
    has_noise = bool(NOISE_REGEX.search(full_text))
    has_finance = bool(FINANCE_REGEX.search(full_text))
    
    # Entity matching
    matched_shareholders = []
    matched_ceos = []
    matched_symbols = set()
    
    # Check shareholder names
    for sh_norm, sh_list in shareholder_map.items():
        if f" {sh_norm} " in f" {norm_text} ":
            for sym, pct in sh_list:
                matched_shareholders.append((sh_norm, sym, pct))
                matched_symbols.add(sym)
                
    # Check CEO names
    for ceo_norm, ceo_list in ceo_map.items():
        if f" {ceo_norm} " in f" {norm_text} ":
            for sym, pos, ctype in ceo_list:
                matched_ceos.append((ceo_norm, sym, pos, ctype))
                matched_symbols.add(sym)

    # Classification logic
    is_entity_backed = len(matched_symbols) > 0 or bool(row['symbol'])
    
    if is_entity_backed:
        category = "FINANCIAL_EQUITY"
        is_relevant = True
    elif has_finance and not has_noise:
        category = "FINANCIAL_MACRO"
        is_relevant = True
    elif has_noise and not has_finance:
        category = "IRRELEVANT_NOISE"
        is_relevant = False
    elif has_noise and has_finance:
        category = "AMBIGUOUS_MIXED"
        is_relevant = True # Keep for safety
    else:
        category = "GENERAL_NEWS"
        is_relevant = False
        
    results.append({
        'source': row['source'],
        'category': category,
        'is_relevant': is_relevant,
        'has_matched_symbols': len(matched_symbols) > 0,
        'matched_symbols': list(matched_symbols),
        'matched_shareholders': len(matched_shareholders),
        'matched_ceos': len(matched_ceos),
    })

res_df = pd.DataFrame(results)
print("\n=== CLASSIFICATION SUMMARY (Sample 3,000 Articles) ===")
print(res_df['category'].value_counts().to_string())

print("\n=== FINANCIAL RELEVANCE SUMMARY ===")
print(res_df['is_relevant'].value_counts().to_string())

print("\n=== BREAKDOWN BY SOURCE ===")
pivot = pd.crosstab(res_df['source'], res_df['category'], margins=True)
print(pivot.to_string())
