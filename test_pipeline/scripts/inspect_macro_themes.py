import sys
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

con = duckdb.connect('db/vesta.duckdb', read_only=True)

macro_themes = {
    "Lãi suất & Chính sách tiền tệ": "SELECT published_at, issuing_body, headline FROM core.macro_policy WHERE regexp_matches(lower(headline), 'lãi suất|tái cấp vốn|tái chiết khấu|trần lãi suất|nới lỏng tiền tệ|thắt chặt tiền tệ') ORDER BY published_at DESC LIMIT 15",
    "Tỷ giá & Tín phiếu & OMO": "SELECT published_at, issuing_body, headline FROM core.macro_policy WHERE regexp_matches(lower(headline), 'tỷ giá|ngoại tệ|bán usd|can thiệp tỷ giá|tín phiếu|hút ròng|bơm ròng|nghiệp vụ thị trường mở') ORDER BY published_at DESC LIMIT 15",
    "Tín dụng & Bất động sản": "SELECT published_at, issuing_body, headline FROM core.macro_policy WHERE regexp_matches(lower(headline), 'room tín dụng|hạn mức tín dụng|tăng trưởng tín dụng|gỡ khó bất động sản|nhà ở xã hội|gói 120.000 tỷ|thông tư 02|thông tư 06') ORDER BY published_at DESC LIMIT 15",
    "Trái phiếu doanh nghiệp & Pháp lý": "SELECT published_at, issuing_body, headline FROM core.macro_policy WHERE regexp_matches(lower(headline), 'trái phiếu doanh nghiệp|nghị định 08|nghị định 65|đảo nợ trái phiếu|gia hạn trái phiếu|áp lực đáo hạn') ORDER BY published_at DESC LIMIT 15",
    "Đầu tư công & Thuế & Tài khóa": "SELECT published_at, issuing_body, headline FROM core.macro_policy WHERE regexp_matches(lower(headline), 'đầu tư công|giải ngân đầu tư công|giảm thuế vat|giảm thuế giá trị gia tăng|chính sách tài khóa') ORDER BY published_at DESC LIMIT 15"
}

for theme, sql in macro_themes.items():
    df = con.execute(sql).df()
    print(f"\n==================== {theme.upper()} ({len(df)} samples) ====================")
    for _, row in df.iterrows():
        pub = str(row['published_at'])[:10] if pd.notnull(row['published_at']) else "N/A"
        print(f"[{pub}] ({row['issuing_body']}): {row['headline']}")

con.close()
