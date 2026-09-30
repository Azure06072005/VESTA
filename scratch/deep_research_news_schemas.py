import duckdb
import sys
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = duckdb.connect('db/vesta_news.duckdb', read_only=True)

tables = ['core.news', 'core.news_resources', 'core.macro_policy', 'core.sector_news_signal']

print("=== 1. CẤU TRÚC VÀ SỐ DÒNG CỦA CÁC BẢNG TIN TỨC TRONG VESTA_NEWS.DUCKDB ===")
for t in tables:
    cnt = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"\n--- Bảng {t} ({cnt:,} dòng) ---")
    desc = con.execute(f"DESCRIBE {t}").fetchdf()
    print(desc[['column_name', 'column_type', 'null', 'key']].to_string())
    print("\nSample 1 row:")
    sample = con.execute(f"SELECT * FROM {t} LIMIT 1").fetchdf()
    for col in sample.columns:
        val = str(sample[col].iloc[0])
        if len(val) > 100:
            val = val[:100] + "..."
        print(f"   * {col:15}: {val}")

print("\n=== 2. THỐNG KÊ NGUỒN TIN (SOURCES) VÀ NGÀY THÁNG ===")
for t in ['core.news', 'core.news_resources', 'core.macro_policy']:
    print(f"\nNguồn trong {t}:")
    try:
        src_df = con.execute(f"SELECT source, min(published_at) as min_pub, max(published_at) as max_pub, count(*) as cnt FROM {t} GROUP BY source ORDER BY cnt DESC LIMIT 10").fetchdf()
        print(src_df.to_string())
    except Exception as e:
        print(f"Error: {e}")

con.close()
