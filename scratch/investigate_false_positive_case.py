import duckdb
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con_news = duckdb.connect("db/vesta_news.duckdb", read_only=True)
row = con_news.execute("""
    SELECT n.source_url, n.headline, r.body
    FROM core.news n
    JOIN core.news_resources r ON n.source_url = r.source_url
    WHERE n.headline LIKE '%FPT%' AND n.headline LIKE '%Ba Huân%'
    LIMIT 1;
""").fetchone()

if row:
    print(f"URL: {row[0]}")
    print(f"HEADLINE: {row[1]}")
    print(f"BODY SNIPPET (first 600 chars):\n{row[2][:600]}")
    print("=" * 60)
    
    # Tìm xem từ Nguyễn Hoàng Minh xuất hiện ở đâu trong body
    idx = row[2].find("Nguyễn Hoàng Minh")
    if idx != -1:
        print(f"Context quanh 'Nguyễn Hoàng Minh':\n{row[2][max(0, idx-100):min(len(row[2]), idx+150)]}")
    else:
        print("Không tìm thấy chính xác 'Nguyễn Hoàng Minh' có dấu, thử tìm không dấu...")

con_news.close()

# Kiểm tra trong vesta_snapshot: Tên Nguyễn Hoàng Minh gắn với công ty nào
con_snap = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)
res_exec = con_snap.execute("""
    SELECT symbol, ceo_name, ceo_position, company_type
    FROM core.company_overview
    WHERE ceo_name LIKE '%Nguyễn Hoàng Minh%'
""").fetchall()
print(f"\nLãnh đạo 'Nguyễn Hoàng Minh' trong company_overview: {res_exec}")

res_sh = con_snap.execute("""
    SELECT symbol, shareholder_name, ownership_percentage
    FROM core.company_shareholders
    WHERE shareholder_name LIKE '%Nguyễn Hoàng Minh%'
""").fetchall()
print(f"Cổ đông 'Nguyễn Hoàng Minh' trong company_shareholders: {res_sh}")
con_snap.close()
