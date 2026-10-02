import sys
import os

# Đảm bảo đường dẫn import src
sys.path.insert(0, os.path.abspath("src"))
sys.stdout.reconfigure(encoding='utf-8')

from pipeline.cross_lakehouse_connector import (
    open_cross_lakehouse,
    query_universe_firewall,
    compute_cross_lakehouse_master_matrix,
    execute_projected_query
)

print("=== KIỂM TOÁN LIÊN KẾT DỮ LIỆU ĐA HỒ (CROSS-LAKEHOUSE DATA MAPPING AUDIT) ===")
print("Áp dụng: Recommendation 1 (Safe ATTACH & Explicit Projection), Recommendation 2 (Universe Integrity Firewall), Recommendation 3 (F105 Integration)")

with open_cross_lakehouse() as con:
    # 1. Kiểm toán Universe Integrity Firewall
    print("\n--- 1. KIỂM TOÁN TƯỜNG LỬA UNIVERSE (UNIVERSE INTEGRITY FIREWALL) ---")
    df_firewall_sample = query_universe_firewall(
        con,
        target_table="core.market_screener_snapshot",
        symbol_col="symbol",
        columns=["symbol", "exchange", "price", "market_cap"],
        where_clause="market_cap > 50000000000000",
        limit=5
    )
    print("Mẫu dữ liệu sau khi đi qua Universe Integrity Firewall (Top vốn hóa > 50K tỷ):")
    for idx, row in df_firewall_sample.iterrows():
        print(f"  • {row['symbol']:<5} | Sàn: {row['exchange']:<6} | Giá: {row['price']:>8,.0f} | Vốn hóa: {row['market_cap']/1e9:,.0f} tỷ")

    # 2. Kiểm toán An toàn Truy vấn Chiếu tường minh (Explicit Projection)
    print("\n--- 2. KIỂM TOÁN AN TOÀN TRUY VẤN (EXPLICIT PROJECTION RAIL) ---")
    try:
        execute_projected_query(con, "SELECT * FROM ohlcv_db.core.market_ohlcv_daily LIMIT 1")
        print("  ❌ Thất bại: Không chặn được SELECT *")
    except ValueError as e:
        print(f"  ✅ Thành công chặn truy vấn cấm: {e}")

    # 3. Tính toán Ma trận Khớp nối Toàn diện Đa hồ (Master Entity Linkage Matrix)
    print("\n--- 3. MA TRẬN KHỚP NỐI THỰC THỂ ĐA HỒ (12 PHÂN LỚP) ---")
    df_matrix = compute_cross_lakehouse_master_matrix(con)
    print(f"{'Phân lớp dữ liệu':<35} | {'Mã trùng khớp':<16} | {'Tỷ lệ Phủ'}")
    print("-" * 75)
    for idx, row in df_matrix.iterrows():
        print(f"{row['dataset']:<35} | {row['matched_symbols']:>5,} / {row['total_dim']:<8,} | {row['match_rate_pct']:>6.2f}%")

    # 4. Kiểm toán Thấu đáo Tin tức F105
    print("\n--- 4. LIÊN KẾT THỰC THỂ TIN TỨC F105 (core.news_entity_map) ---")
    total_news = con.execute("SELECT count(*) FROM news_db.core.news").fetchone()[0]
    total_entity_links = con.execute("SELECT count(*) FROM news_db.core.news_entity_map").fetchone()[0]
    distinct_syms_f105 = con.execute("SELECT count(DISTINCT symbol) FROM news_db.core.news_entity_map WHERE symbol IS NOT NULL").fetchone()[0]
    
    print(f"  • Tổng bài viết tin tức: {total_news:,} bài")
    print(f"  • Tổng liên kết thực thể (F105 3NF): {total_entity_links:,} liên kết")
    print(f"  • Số mã chứng khoán được giải mã thành công: {distinct_syms_f105:,} mã")

print("\n=== HOÀN TẤT KIỂM TOÁN DỮ LIỆU ĐA HỒ ===")
