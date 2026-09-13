import json
import sys
from pathlib import Path
import pandas as pd
import duckdb

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(r"d:\VESTA\src")))

from crawlers.dim_symbol import _authenticate
_authenticate()
import vnstock as vs

# 1. Fetch vnstock sectors
print("1. Fetching vnstock sectors...")
ref = vs.Reference()
df_vnstock = ref.industry.sectors()
print(f"   vnstock returned {len(df_vnstock)} symbols.")

# 2. Sector Taxonomy Definition (25 Vietstock Sectors)
SECTOR_TAXONOMY = [
    {"sector_id": 3, "sector_name": "Bất động sản", "english_name": "Real Estate", "gics_sector_code": "60", "url_slug": "3-bat-dong-san", "keywords": ["bất động sản", "địa ốc", "bđs", "nhà đất", "đô thị", "chung cư", "bất động sản khu công nghiệp"]},
    {"sector_id": 5, "sector_name": "Chứng khoán", "english_name": "Securities", "gics_sector_code": "40", "url_slug": "5-chung-khoan", "keywords": ["chứng khoán", "ctck", "môi giới chứng khoán", "công ty chứng khoán"]},
    {"sector_id": 11, "sector_name": "Ngân hàng", "english_name": "Banking", "gics_sector_code": "40", "url_slug": "11-ngan-hang", "keywords": ["ngân hàng", "nhà băng", "ngân hàng thương mại", "tín dụng"]},
    {"sector_id": 21, "sector_name": "Vật liệu xây dựng", "english_name": "Materials & Steel", "gics_sector_code": "15", "url_slug": "21-vat-lieu-xay-dung", "keywords": ["thép", "kim loại", "vật liệu xây dựng", "xi măng", "tôn mạ"]},
    {"sector_id": 24, "sector_name": "Xây dựng", "english_name": "Construction", "gics_sector_code": "20", "url_slug": "24-xay-dung", "keywords": ["xây dựng", "xây lắp", "nhà thầu", "hạ tầng", "đầu tư công"]},
    {"sector_id": 10, "sector_name": "Khai khoáng", "english_name": "Mining & Oil Gas", "gics_sector_code": "10", "url_slug": "10-khai-khoang", "keywords": ["dầu khí", "khai khoáng", "than", "xăng dầu", "khí đốt"]},
    {"sector_id": 18, "sector_name": "SX Nhựa - Hóa chất", "english_name": "Chemicals & Fertilizers", "gics_sector_code": "15", "url_slug": "18-sx-nhua-hoa-chat", "keywords": ["hóa chất", "phân bón", "nhựa", "phốt pho", "đạm"]},
    {"sector_id": 6, "sector_name": "Công nghệ và thông tin", "english_name": "Information Technology", "gics_sector_code": "45", "url_slug": "6-cong-nghe-va-thong-tin", "keywords": ["công nghệ thông tin", "phần mềm", "viễn thông", "cntt", "chuyển đổi số"]},
    {"sector_id": 7, "sector_name": "Bán lẻ", "english_name": "Retail", "gics_sector_code": "25", "url_slug": "7-ban-le", "keywords": ["bán lẻ", "chuỗi bán lẻ", "siêu thị"]},
    {"sector_id": 19, "sector_name": "Thực phẩm - Đồ uống", "english_name": "Food & Beverage", "gics_sector_code": "30", "url_slug": "19-thuc-pham-do-uong", "keywords": ["thực phẩm", "đồ uống", "sữa", "bia", "thịt lợn", "đường", "chăn nuôi"]},
    {"sector_id": 20, "sector_name": "Chế biến Thủy sản", "english_name": "Seafood", "gics_sector_code": "30", "url_slug": "20-che-bien-thuy-san", "keywords": ["thủy sản", "thủy hải sản", "tôm", "cá tra", "xuất khẩu thủy sản"]},
    {"sector_id": 23, "sector_name": "Vận tải - kho bãi", "english_name": "Transportation & Logistics", "gics_sector_code": "20", "url_slug": "23-van-tai-kho-bai", "keywords": ["vận tải", "kho bãi", "logistics", "cảng biển", "vận tải biển", "hàng không"]},
    {"sector_id": 22, "sector_name": "Tiện ích", "english_name": "Utilities & Energy", "gics_sector_code": "55", "url_slug": "22-tien-ich", "keywords": ["tiện ích", "năng lượng", "điện", "nước", "cấp thoát nước", "năng lượng tái tạo"]},
    {"sector_id": 8, "sector_name": "Chăm sóc sức khỏe", "english_name": "Healthcare & Pharmaceuticals", "gics_sector_code": "35", "url_slug": "8-cham-soc-suc-khoe", "keywords": ["chăm sóc sức khỏe", "dược phẩm", "y tế", "thuốc"]},
    {"sector_id": 2, "sector_name": "Bảo hiểm", "english_name": "Insurance", "gics_sector_code": "40", "url_slug": "2-bao-hiem", "keywords": ["bảo hiểm", "phi nhân thọ"]},
    {"sector_id": 16, "sector_name": "SX Hàng gia dụng", "english_name": "Textile & Household Goods", "gics_sector_code": "25", "url_slug": "16-sx-hang-gia-dung", "keywords": ["dệt may", "may mặc", "hàng gia dụng", "sợi"]},
    {"sector_id": 17, "sector_name": "Sản phẩm cao su", "english_name": "Rubber Products", "gics_sector_code": "15", "url_slug": "17-san-pham-cao-su", "keywords": ["cao su", "mủ cao su", "săm lốp"]},
    {"sector_id": 12, "sector_name": "Nông - Lâm - Ngư", "english_name": "Agriculture & Forestry", "gics_sector_code": "30", "url_slug": "12-nong-lam-ngu", "keywords": ["nông nghiệp", "lâm sản", "gỗ", "trồng trọt"]},
    {"sector_id": 1, "sector_name": "Bán buôn", "english_name": "Wholesale", "gics_sector_code": "20", "url_slug": "1-ban-buon", "keywords": ["bán buôn", "thương mại"]},
    {"sector_id": 26, "sector_name": "SX Phụ trợ", "english_name": "Supporting Manufacturing", "gics_sector_code": "20", "url_slug": "26-sx-phu-tro", "keywords": ["sản xuất phụ trợ", "công nghiệp phụ trợ"]},
    {"sector_id": 27, "sector_name": "Thiết bị điện", "english_name": "Electrical Equipment", "gics_sector_code": "20", "url_slug": "27-thiet-bi-dien", "keywords": ["thiết bị điện", "dây cáp điện"]},
    {"sector_id": 15, "sector_name": "SX Thiết bị, máy móc", "english_name": "Machinery & Equipment", "gics_sector_code": "20", "url_slug": "15-sx-thiet-bi-may-moc", "keywords": ["máy móc", "thiết bị công nghiệp"]},
    {"sector_id": 25, "sector_name": "Dịch vụ lưu trú, ăn uống, giải trí", "english_name": "Hospitality & Entertainment", "gics_sector_code": "25", "url_slug": "25-dich-vu-luu-tru-an-uong-giai-tri", "keywords": ["du lịch", "khách sạn", "nghỉ dưỡng", "giải trí"]},
    {"sector_id": 28, "sector_name": "Dịch vụ tư vấn, hỗ trợ", "english_name": "Consulting & Support", "gics_sector_code": "20", "url_slug": "28-dich-vu-tu-van-ho-tro", "keywords": ["tư vấn", "dịch vụ hỗ trợ"]},
    {"sector_id": 29, "sector_name": "Tài chính khác", "english_name": "Other Financials", "gics_sector_code": "40", "url_slug": "29-tai-chinh-khac", "keywords": ["quản lý quỹ", "tài chính khác"]}
]

# 3. Prepare Symbol-to-Sector DataFrame in memory
records = []
for _, r in df_vnstock.iterrows():
    records.append({
        "symbol": str(r["symbol"]),
        "sector_id": int(r["industry_code"]),
        "sector_name": str(r["industry_name"]),
        "source": "vnstock"
    })

# Anfin mapping
ANFIN_TO_SECTOR_ID = {
    "1. Ngành Ngân hàng": 11,
    "2. Ngành Chứng khoán": 5,
    "3. Ngành Công nghệ thông tin": 6,
    "4. Ngành Bưu chính - Viễn thông": 6,
    "5. Ngành Y tế - Dược phẩm": 8,
    "6. Ngành Điện - Năng lượng": 22,
    "7. Ngành Dầu khí": 10,
    "8. Ngành Xây dựng": 24,
    "9. Ngành Đầu tư công": 24,
    "10. Ngành Thép - Kim loại": 21,
    "11. Ngành Than - Khoáng sản": 10,
    "12. Ngành Du lịch": 25,
    "13. Ngành Hàng không": 23,
    "14. Ngành Bán lẻ - Hàng tiêu dùng": 7,
    "15. Ngành Thực phẩm": 19,
    "16. Ngành Giao thông vận tải": 23,
    "17. Ngành Thủy hải sản": 20,
    "18. Ngành Bảo hiểm": 2,
    "19. Ngành Dệt - May mặc": 16,
    "20. Ngành Truyền thông giải trí": 25,
    "21. Ngành Cao su": 17,
}

df_anfin = pd.read_csv(r"d:\VESTA\scratch\anfin_sectors_parsed.csv")
seen_symbols = {r["symbol"] for r in records}
added_anfin = 0

sec_name_lookup = {s["sector_id"]: s["sector_name"] for s in SECTOR_TAXONOMY}

for _, r in df_anfin.iterrows():
    sym = str(r["symbol"])
    hdr = str(r["sector_header"])
    if sym not in seen_symbols and hdr in ANFIN_TO_SECTOR_ID:
        target_id = ANFIN_TO_SECTOR_ID[hdr]
        records.append({
            "symbol": sym,
            "sector_id": target_id,
            "sector_name": sec_name_lookup[target_id],
            "source": "anfin"
        })
        seen_symbols.add(sym)
        added_anfin += 1

print(f"2. Prepared {len(records)} total symbols ({added_anfin} supplemental from Anfin).")

# 4. Open staging DB and bulk insert in one batch
con = duckdb.connect(r"d:\VESTA\db\staging_sync.duckdb")

# Table DDLs
con.execute("""
CREATE TABLE IF NOT EXISTS core.dim_sector (
    sector_id        INTEGER NOT NULL PRIMARY KEY,
    sector_name      VARCHAR NOT NULL,
    english_name     VARCHAR,
    gics_sector_code VARCHAR,
    url_slug         VARCHAR,
    keywords_json    VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS core.dim_symbol_sector (
    symbol           VARCHAR NOT NULL PRIMARY KEY,
    sector_id        INTEGER NOT NULL,
    sector_name      VARCHAR NOT NULL,
    source           VARCHAR NOT NULL,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS core.sector_news_signal (
    source_url       VARCHAR NOT NULL,
    sector_id        INTEGER NOT NULL,
    sector_name      VARCHAR NOT NULL,
    matched_keyword  VARCHAR NOT NULL,
    match_tier       VARCHAR NOT NULL,
    market_anchor    VARCHAR NOT NULL,
    fetched_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (source_url, sector_id)
);
""")

# Bulk insert dim_sector
df_tax = pd.DataFrame([
    {
        "sector_id": s["sector_id"],
        "sector_name": s["sector_name"],
        "english_name": s["english_name"],
        "gics_sector_code": s["gics_sector_code"],
        "url_slug": s["url_slug"],
        "keywords_json": json.dumps(s["keywords"], ensure_ascii=False)
    }
    for s in SECTOR_TAXONOMY
])
con.execute("DELETE FROM core.dim_sector")
con.register("df_tax_view", df_tax)
con.execute("INSERT INTO core.dim_sector SELECT * FROM df_tax_view")
con.unregister("df_tax_view")

# Bulk insert dim_symbol_sector
df_sym_sec = pd.DataFrame(records)
con.execute("DELETE FROM core.dim_symbol_sector")
con.register("df_sym_sec_view", df_sym_sec)
con.execute("""
INSERT INTO core.dim_symbol_sector (symbol, sector_id, sector_name, source, updated_at)
SELECT symbol, sector_id, sector_name, source, CURRENT_TIMESTAMP FROM df_sym_sec_view
""")
con.unregister("df_sym_sec_view")

print("3. Successfully populated database tables.")
print("\n=== SUMMARY OF STAGING DATABASE ===")
print(con.execute("SELECT count(*) as total_sectors FROM core.dim_sector").df())
print(con.execute("SELECT count(*) as total_symbol_mappings, source, count(*) as count FROM core.dim_symbol_sector GROUP BY source").df())
print("\nTop 10 sectors by stock count:")
print(con.execute("""
    SELECT sector_id, sector_name, count(*) as stock_count 
    FROM core.dim_symbol_sector 
    GROUP BY sector_id, sector_name 
    ORDER BY stock_count DESC 
    LIMIT 10
""").df().to_string())

con.close()
