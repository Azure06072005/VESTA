"""
Nghiên cứu chuyên sâu F102: Quy trình ghép nối Point-In-Time (PIT Join) trên 3 hồ dữ liệu Lakehouse VESTA.
Khảo sát và định lượng 4 vấn đề kỹ thuật trọng yếu:
1. Tri-Lakehouse ATTACH Pattern & Cross-Database View Isolation
2. Tác động của hệ số điều chỉnh giá CAF (Dual-mode Price Adjustment) lên tỷ suất sinh lời T+1, T+5, T+30
3. Xử lý triệt để dị thường giá bằng 0 (Zero-Price) và phiên khối lượng bằng 0 (Zero-Volume Bars)
4. Đánh giá Look-Ahead Bias của tin tức mốc giờ nửa đêm (00:00:00) và quy tắc Forward-Lagging
"""
import sys
import os
import duckdb
import pandas as pd
import numpy as np
import datetime as dt

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("DEEP RESEARCH F102: POINT-IN-TIME (PIT) NEWS + PRICE + FUNDAMENTALS JOIN")
print("=" * 80)

# 1. Khởi tạo kết nối Tri-Lakehouse
con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_news.duckdb' AS news_db (READ_ONLY);")

print("\n--- [1] KHẢO SÁT QUY MÔ THỰC TẾ & TIỀM NĂNG GHÉP NỐI (DATA JOIN UNIVERSE) ---")

# Kiểm tra số lượng mã có đầy đủ 3 chân dữ liệu: Tin tức, Nến ngày, BCTC
sym_news = con.execute("SELECT count(DISTINCT symbol) FROM news_db.core.news WHERE symbol IS NOT NULL").fetchone()[0]
sym_ohlcv = con.execute("SELECT count(DISTINCT symbol) FROM ohlcv_db.core.market_ohlcv_daily").fetchone()[0]
sym_fund = con.execute("SELECT count(DISTINCT symbol) FROM core.fundamentals").fetchone()[0]
sym_adj = con.execute("SELECT count(DISTINCT symbol) FROM core.price_adjustment_events").fetchone()[0]

print(f"  • Số mã cổ phiếu có Tin tức (vesta_news)               : {sym_news:,} mã")
print(f"  • Số mã cổ phiếu có Nến ngày OHLCV (vesta_ohlcv)       : {sym_ohlcv:,} mã")
print(f"  • Số mã cổ phiếu có BCTC Fundamentals (vesta_snapshot) : {sym_fund:,} mã")
print(f"  • Số mã cổ phiếu có Sự kiện điều chỉnh CAF            : {sym_adj:,} mã")

# Tìm giao thoa 3 chân
common_syms = con.execute("""
    SELECT count(DISTINCT n.symbol)
    FROM news_db.core.news n
    INNER JOIN (SELECT DISTINCT symbol FROM ohlcv_db.core.market_ohlcv_daily) o ON n.symbol = o.symbol
    INNER JOIN (SELECT DISTINCT symbol FROM core.fundamentals) f ON n.symbol = f.symbol
    WHERE n.symbol IS NOT NULL
""").fetchone()[0]
print(f"  • Số mã cổ phiếu giao thoa đủ cả 3 chân (News + OHLCV + BCTC): {common_syms:,} mã")

# Kiểm tra tổng số bài báo có thể ghép nối
joinable_news = con.execute("""
    SELECT count(*)
    FROM news_db.core.news n
    INNER JOIN (SELECT DISTINCT symbol FROM ohlcv_db.core.market_ohlcv_daily) o ON n.symbol = o.symbol
    WHERE n.symbol IS NOT NULL AND n.duplicate_of IS NULL
""").fetchone()[0]
print(f"  • Tổng số bài viết tin tức hợp lệ sẵn sàng ghép nối PIT: {joinable_news:,} bài viết")

print("\n--- [2] ĐỊNH LƯỢNG TÁC ĐỘNG CỦA HỆ SỐ ĐIỀU CHỈNH GIÁ (CAF ADJUSTMENTS) ---")

# Khảo sát sự khác biệt giữa Giá gốc (Raw Close) và Giá điều chỉnh (Adj Close)
adj_sample = con.execute("""
    SELECT 
        symbol,
        count(*) as total_adj_events,
        min(ex_date) as earliest_adj,
        max(ex_date) as latest_adj,
        min(multiplier) as min_mult,
        min(cumulative_adjustment_factor) as min_caf
    FROM core.price_adjustment_events
    WHERE symbol IN ('FPT', 'VNM', 'HPG', 'VCB', 'SSI')
    GROUP BY symbol
""").df()
print("Mẫu sự kiện điều chỉnh giá (CAF) trên các mã Bluechips VN30:")
print(adj_sample.to_string(index=False))

# Kiểm tra một sự kiện chia tách cụ thể của HPG hoặc FPT
hpg_adj = con.execute("""
    SELECT symbol, ex_date, adjustment_type, cash_dividend, stock_dividend_ratio, multiplier, cumulative_adjustment_factor
    FROM core.price_adjustment_events
    WHERE symbol = 'HPG'
    ORDER BY ex_date DESC
    LIMIT 5
""").df()
print("\n5 sự kiện điều chỉnh giá gần nhất của HPG (Minh họa tác động chia cổ tức/thưởng):")
print(hpg_adj.to_string(index=False))

print("\n--- [3] KHẢO SÁT & ĐỊNH LƯỢNG 4 DATA CAVEATS TRONG PIT_EVENTS ---")

# A. Zero price analysis
zero_price_cnt = con.execute("SELECT count(*) FROM core.pit_events WHERE price_at_publish <= 0").fetchone()[0]
null_price_cnt = con.execute("SELECT count(*) FROM core.pit_events WHERE price_at_publish IS NULL").fetchone()[0]
valid_price_cnt = con.execute("SELECT count(*) FROM core.pit_events WHERE price_at_publish > 0").fetchone()[0]
total_pit = con.execute("SELECT count(*) FROM core.pit_events").fetchone()[0]

print(f"1. Giá công bố (price_at_publish):")
print(f"   • Hợp lệ (> 0)  : {valid_price_cnt:,} ({valid_price_cnt/total_pit*100:.2f}%)")
print(f"   • Bằng 0 (<= 0) : {zero_price_cnt:,} ({zero_price_cnt/total_pit*100:.2f}%)")
print(f"   • Rỗng (NULL)   : {null_price_cnt:,} ({null_price_cnt/total_pit*100:.2f}%)")

# B. Zero volume analysis trên OHLCV
zero_vol_cnt = con.execute("SELECT count(*) FROM ohlcv_db.core.market_ohlcv_daily WHERE volume <= 0").fetchone()[0]
total_ohlcv = con.execute("SELECT count(*) FROM ohlcv_db.core.market_ohlcv_daily").fetchone()[0]
print(f"\n2. Khối lượng nến ngày (OHLCV Volume):")
print(f"   • Phiên volume <= 0: {zero_vol_cnt:,} / {total_ohlcv:,} ({zero_vol_cnt/total_ohlcv*100:.2f}%)")

# C. Midnight timestamps (00:00:00) analysis
midnight_news = con.execute("""
    SELECT 
        strftime(published_at, '%H:%M:%S') = '00:00:00' as is_midnight,
        count(*) as cnt,
        min(published_at) as min_dt,
        max(published_at) as max_dt
    FROM news_db.core.news
    WHERE symbol IS NOT NULL
    GROUP BY is_midnight
""").df()
print(f"\n3. Phân bố mốc thời gian tin tức theo giờ:")
print(midnight_news.to_string(index=False))

# D. Fundamentals coverage in PIT events
fund_coverage = con.execute("""
    SELECT 
        count(CASE WHEN fundamentals_json IS NOT NULL AND fundamentals_json != '{}' THEN 1 END) as with_fund,
        count(*) as total
    FROM core.pit_events
""").df()
print(f"\n4. Độ phủ BCTC trong pit_events hiện tại:")
print(f"   • Có BCTC đính kèm : {fund_coverage['with_fund'][0]:,} / {fund_coverage['total'][0]:,} ({fund_coverage['with_fund'][0]/fund_coverage['total'][0]*100:.4f}%)")

print("\n--- [4] THỬ NGHIỆM ĐỊNH LƯỢNG QUY TẮC FORWARD-LAGGING CHO MỐC 00:00:00 ---")

# Lấy mẫu các tin tức 00:00:00 của FPT và đo lường sự chênh lệch lợi nhuận giữa Same-Day vs Next-Day Anchor
sim_query = """
    WITH fpt_news AS (
        SELECT source_url, published_at, headline
        FROM news_db.core.news
        WHERE symbol = 'FPT' AND strftime(published_at, '%H:%M:%S') = '00:00:00'
        LIMIT 100
    ),
    fpt_prices AS (
        SELECT date, close
        FROM ohlcv_db.core.market_ohlcv_daily
        WHERE symbol = 'FPT'
    )
    SELECT 
        n.published_at,
        n.headline,
        p_same.close as same_day_close,
        p_next.close as next_day_close,
        (p_next.close - p_same.close) / p_same.close * 100 as overnight_gap_pct
    FROM fpt_news n
    LEFT JOIN fpt_prices p_same ON CAST(n.published_at AS DATE) = p_same.date
    LEFT JOIN fpt_prices p_next ON CAST(n.published_at + INTERVAL 1 DAY AS DATE) = p_next.date
    WHERE p_same.close IS NOT NULL AND p_next.close IS NOT NULL
    LIMIT 10
"""
try:
    sim_df = con.execute(sim_query).df()
    print("Mẫu 10 tin tức FPT mốc 00:00:00 so sánh giá Same-Day Close vs Next-Day Close:")
    print(sim_df[['published_at', 'same_day_close', 'next_day_close', 'overnight_gap_pct']].to_string(index=False))
except Exception as e:
    print(f"Lỗi khi mô phỏng: {e}")

con.close()
print("\n" + "=" * 80)
print("HOÀN TẤT KHẢO SÁT THỰC NGHIỆM DEEP RESEARCH F102")
print("=" * 80)
