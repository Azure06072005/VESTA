import duckdb
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
df = con.execute("SELECT symbol, organ_name, en_organ_name FROM core.dim_symbol").df()
con.close()

print(f"Tổng số mã trong dim_symbol: {len(df)}")

# Thử trích xuất short name
single_word_orgs = []
multi_word_orgs = []

for _, row in df.iterrows():
    sym = row['symbol']
    raw_org = str(row['organ_name']).strip()
    short_org = re.sub(
        r"^(công ty cổ phần|ctcp|tập đoàn|ngân hàng thương mại cổ phần|ngân hàng tmcp|tổng công ty|tct)\s*",
        "", raw_org, flags=re.IGNORECASE
    ).strip()
    words = short_org.split()
    if len(words) == 1:
        single_word_orgs.append((sym, raw_org, short_org))
    else:
        multi_word_orgs.append((sym, raw_org, short_org))

print(f"\nSố doanh nghiệp có tên ngắn gọn chỉ có 1 TỪ (bị F105 loại bỏ hoàn toàn): {len(single_word_orgs)}")
print("Ví dụ 30 doanh nghiệp 1 từ tiêu biểu bị loại bỏ:")
for sym, raw, short in single_word_orgs[:30]:
    print(f"  - [{sym}]: '{short}' (gốc: '{raw}')")

print(f"\nSố doanh nghiệp có tên >= 2 từ: {len(multi_word_orgs)}")
