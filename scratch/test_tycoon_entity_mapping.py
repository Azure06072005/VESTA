import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb
import re
import pandas as pd

# Connect to snapshot / backup to load entities
con_snap = duckdb.connect('db/vesta_backup.duckdb', read_only=True)

# 1. Load shareholders
df_shareholders = con_snap.execute("""
    SELECT DISTINCT symbol, trim(shareholder_name) as name, ownership_percentage
    FROM core.company_shareholders
    WHERE shareholder_name IS NOT NULL AND length(trim(shareholder_name)) >= 4
""").df()

# 2. Load company overview
df_overview = con_snap.execute("""
    SELECT symbol, ceo_name, ceo_position, inspector_name, inspector_position, company_type
    FROM core.company_overview
""").df()

# 3. Load dim_symbol (company names)
df_symbols = con_snap.execute("""
    SELECT symbol, organ_name, en_organ_name, industry_name
    FROM core.dim_symbol
""").df()

con_snap.close()

print(f"Loaded {len(df_shareholders)} shareholder records, {len(df_overview)} overview records, {len(df_symbols)} symbols.")

# Let's inspect some top tycoons / founders / CEOs
tycoons = [
    ("Phạm Nhật Vượng", "VIC"),
    ("Trần Đình Long", "HPG"),
    ("Nguyễn Đăng Quang", "MSN"),
    ("Hồ Hùng Anh", "TCB"),
    ("Trương Gia Bình", "FPT"),
    ("Nguyễn Thị Phương Thảo", "VJC"),
    ("Đoàn Nguyên Đức", "HAG"),
    ("Bùi Thành Nhơn", "NVL"),
    ("Đặng Thành Tâm", "KBC"),
    ("Nguyễn Đức Tài", "MWG"),
]

# Connect to news db and search for occurrences in news headlines & bodies
con_news = duckdb.connect('db/vesta_news.duckdb', read_only=True)

print("\n=== SCANNING TYCOON MENTIONS IN NEWS ===")
for name, sym in tycoons:
    res = con_news.execute(f"""
        SELECT 
            count(*) as total_mentions,
            count(CASE WHEN symbol = '{sym}' THEN 1 END) as already_tagged,
            count(CASE WHEN symbol IS NULL OR symbol = '' THEN 1 END) as untagged
        FROM core.news
        WHERE regexp_matches(headline, '(?i){name}') 
           OR (body IS NOT NULL AND regexp_matches(body, '(?i){name}'))
    """).fetchone()
    print(f"[{sym}] {name:25s}: Total {res[0]:4d} mentions | Already tagged: {res[1]:3d} | Untagged (Recoverable!): {res[2]:3d}")

con_news.close()
