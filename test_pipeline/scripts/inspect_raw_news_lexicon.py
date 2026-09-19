import sys
sys.stdout.reconfigure(encoding='utf-8')
import duckdb
import pandas as pd
import re
from collections import Counter

con = duckdb.connect("db/vesta.duckdb", read_only=True)
print("Querying distinct headline keywords across full historical core.news (661k)...")

queries = {
    "Tin tốt nhưng giá xấu / Bẫy": "SELECT headline, published_at FROM core.news WHERE regexp_matches(lower(headline), 'tin tốt|kỷ lục|vượt đỉnh|lãi khủng|kéo trụ|xả hàng|bẫy tăng|bull trap|úp bô|chốt lời|phân phối') ORDER BY published_at DESC LIMIT 30",
    "Tin xấu nhưng tạo đáy / Rũ bỏ": "SELECT headline, published_at FROM core.news WHERE regexp_matches(lower(headline), 'rũ bỏ|ép cung|cạn cung|bắt đáy|giải chấp diện rộng|lau sàn|hoảng loạn|tháo chạy|tạo đáy|rũ sạch') ORDER BY published_at DESC LIMIT 30",
    "Pháp lý / Thanh tra / Khởi tố": "SELECT headline, published_at FROM core.news WHERE regexp_matches(lower(headline), 'khởi tố|bắt tạm giam|thanh tra|kết luận thanh tra|xử phạt|vi phạm|hủy niêm yết|đình chỉ|cưỡng chế') ORDER BY published_at DESC LIMIT 30",
    "Tái cơ cấu / Đảo nợ / M&A": "SELECT headline, published_at FROM core.news WHERE regexp_matches(lower(headline), 'thay máu|đảo nợ|gia hạn trái phiếu|tái cơ cấu|bán tài sản|chuyển nhượng|thâu tóm|chào mua công khai') ORDER BY published_at DESC LIMIT 30"
}

for cat, sql in queries.items():
    res = con.execute(sql).fetchall()
    print(f"\n==================== {cat} ({len(res)} samples) ====================")
    for row in res[:8]:
        print(f"[{row[1].strftime('%Y-%m-%d') if row[1] else 'N/A'}] {row[0]}")

con.close()
