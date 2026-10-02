"""
Nghiên cứu chuyên sâu F101: Khung thẩm định chất lượng dữ liệu đa tầng (Tiered Validation Penalty Framework).
Khảo sát thực nghiệm trên 3 hồ dữ liệu Lakehouse của VESTA:
- vesta_snapshot.duckdb
- vesta_ohlcv.duckdb
- vesta_news.duckdb
"""
import sys
import duckdb
import pandas as pd
import numpy as np
import datetime as dt

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("DEEP RESEARCH F101: TIERED VALIDATION PENALTY & DATA QUALITY SCORING (DQS)")
print("=" * 80)

# 1. Kết nối 3 hồ DuckDB
con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_news.duckdb' AS news_db (READ_ONLY);")

print("\n--- [1] KHẢO SÁT CÁC ĐIỂM DỊ THƯỜNG & KHUYẾT TẬT DỮ LIỆU THỰC TẾ ---")

# A. Bảng core.market_ohlcv_daily (ohlcv_db)
ohlcv_stats = con.execute("""
    SELECT 
        count(*) as total_rows,
        count(CASE WHEN volume <= 0 THEN 1 END) as zero_volume_rows,
        count(CASE WHEN close <= 0 OR open <= 0 OR high <= 0 OR low <= 0 THEN 1 END) as non_positive_price_rows,
        count(CASE WHEN high < low OR high < open OR high < close OR low > open OR low > close THEN 1 END) as invalid_geometry_rows,
        count(CASE WHEN CAST(date AS TIMESTAMP) > CURRENT_TIMESTAMP THEN 1 END) as future_date_rows
    FROM ohlcv_db.core.market_ohlcv_daily
""").df()
print("\n[A] Dữ liệu Nến ngày (core.market_ohlcv_daily):")
print(f"  • Tổng số dòng: {ohlcv_stats['total_rows'][0]:,}")
print(f"  • Phiên khối lượng volume <= 0: {ohlcv_stats['zero_volume_rows'][0]:,} ({ohlcv_stats['zero_volume_rows'][0]/ohlcv_stats['total_rows'][0]*100:.2f}%)")
print(f"  • Dòng có giá âm hoặc bằng 0: {ohlcv_stats['non_positive_price_rows'][0]:,} ({ohlcv_stats['non_positive_price_rows'][0]/ohlcv_stats['total_rows'][0]*100:.4f}%)")
print(f"  • Dòng sai cấu trúc nến (High < Low/Open/Close): {ohlcv_stats['invalid_geometry_rows'][0]:,} ({ohlcv_stats['invalid_geometry_rows'][0]/ohlcv_stats['total_rows'][0]*100:.4f}%)")
print(f"  • Dòng có ngày trong tương lai: {ohlcv_stats['future_date_rows'][0]:,}")

# B. Bảng core.news (news_db)
news_stats = con.execute("""
    SELECT 
        count(*) as total_news,
        count(CASE WHEN body IS NULL OR length(trim(body)) < 20 THEN 1 END) as empty_body_news,
        count(CASE WHEN strftime(published_at, '%H:%M:%S') = '00:00:00' THEN 1 END) as midnight_timestamp_news,
        count(CASE WHEN symbol IS NULL THEN 1 END) as untagged_news,
        count(CASE WHEN published_at > fetched_at THEN 1 END) as lookahead_timing_news
    FROM news_db.core.news
""").df()
print("\n[B] Dữ liệu Tin tức (core.news):")
print(f"  • Tổng số bài viết: {news_stats['total_news'][0]:,}")
print(f"  • Bài viết không có thân bài hoặc quá ngắn (<20 ký tự): {news_stats['empty_body_news'][0]:,} ({news_stats['empty_body_news'][0]/news_stats['total_news'][0]*100:.2f}%)")
print(f"  • Bài viết có mốc giờ nửa đêm 00:00:00 (cần lag session): {news_stats['midnight_timestamp_news'][0]:,} ({news_stats['midnight_timestamp_news'][0]/news_stats['total_news'][0]*100:.2f}%)")
print(f"  • Bài viết không gán mã (tin vĩ mô/ngành): {news_stats['untagged_news'][0]:,} ({news_stats['untagged_news'][0]/news_stats['total_news'][0]*100:.2f}%)")
print(f"  • Bài viết vi phạm thứ tự thời gian (published > fetched): {news_stats['lookahead_timing_news'][0]:,}")

# C. Bảng core.pit_events (vesta_snapshot)
pit_exists = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='core' AND table_name='pit_events'").fetchone()[0]
if pit_exists:
    pit_stats = con.execute("""
        SELECT 
            count(*) as total_events,
            count(CASE WHEN price_at_publish <= 0 OR price_at_publish IS NULL THEN 1 END) as zero_publish_price,
            count(CASE WHEN price_t1 IS NULL THEN 1 END) as null_t1,
            count(CASE WHEN price_t5 IS NULL THEN 1 END) as null_t5,
            count(CASE WHEN price_t30 IS NULL THEN 1 END) as null_t30,
            count(CASE WHEN fundamentals_json IS NULL OR fundamentals_json = '{}' THEN 1 END) as missing_fundamentals
        FROM core.pit_events
    """).df()
    print("\n[C] Dữ liệu Sự kiện Point-in-Time (core.pit_events):")
    print(f"  • Tổng số sự kiện PIT: {pit_stats['total_events'][0]:,}")
    print(f"  • Sự kiện có giá công bố <= 0 hoặc NULL: {pit_stats['zero_publish_price'][0]:,} ({pit_stats['zero_publish_price'][0]/pit_stats['total_events'][0]*100:.3f}%)")
    print(f"  • Sự kiện thiếu giá T+1: {pit_stats['null_t1'][0]:,} ({pit_stats['null_t1'][0]/pit_stats['total_events'][0]*100:.2f}%)")
    print(f"  • Sự kiện thiếu giá T+5 (do nến tương lai chưa đủ): {pit_stats['null_t5'][0]:,} ({pit_stats['null_t5'][0]/pit_stats['total_events'][0]*100:.2f}%)")
    print(f"  • Sự kiện thiếu giá T+30: {pit_stats['null_t30'][0]:,} ({pit_stats['null_t30'][0]/pit_stats['total_events'][0]*100:.2f}%)")
    print(f"  • Sự kiện thiếu BCTC kết nối: {pit_stats['missing_fundamentals'][0]:,} ({pit_stats['missing_fundamentals'][0]/pit_stats['total_events'][0]*100:.2f}%)")

print("\n--- [2] THỬ NGHIỆM MÔ PHỎNG TIERED DATA QUALITY SCORING (DQS) ---")

# Lấy 1 mẫu 50,000 sự kiện PIT để đánh giá phân phối điểm chất lượng DQS
sample_df = con.execute("""
    SELECT 
        e.symbol,
        e.source_url,
        e.price_at_publish,
        e.price_t1,
        e.price_t5,
        e.price_t30,
        e.fundamentals_json,
        n.published_at,
        n.fetched_at,
        n.body,
        strftime(n.published_at, '%H:%M:%S') as pub_time
    FROM core.pit_events e
    JOIN news_db.core.news n ON e.source_url = n.source_url
    LIMIT 50000
""").df()

# Hàm tính Data Quality Score
def evaluate_tiered_dqs(row):
    penalties = 0.0
    flags = []
    
    # Tier 1: Fatal Errors (Penalty: 1.0 -> Exclude completely)
    if row['price_at_publish'] is None or row['price_at_publish'] <= 0:
        penalties += 1.0
        flags.append("TIER1_ZERO_PRICE")
    if row['published_at'] > row['fetched_at'] + dt.timedelta(minutes=5):
        penalties += 1.0
        flags.append("TIER1_LOOKAHEAD_TIMING")
        
    if penalties >= 1.0:
        return 0.0, " | ".join(flags), "TIER_1_REJECT"
        
    # Tier 2: Structural Flaws (Penalty: 0.40)
    if row['price_t1'] is None:
        penalties += 0.40
        flags.append("TIER2_MISSING_T1_RETURN")
        
    # Tier 3: Metadata / Incompleteness Flaws (Penalty: 0.15 - 0.20)
    if row['pub_time'] == '00:00:00':
        penalties += 0.20
        flags.append("TIER3_MIDNIGHT_TIMESTAMP")
    if row['body'] is None or len(str(row['body']).strip()) < 50:
        penalties += 0.15
        flags.append("TIER3_HEADLINE_ONLY")
    if row['fundamentals_json'] is None or row['fundamentals_json'] == '{}':
        penalties += 0.15
        flags.append("TIER3_MISSING_BCTC")
        
    # Tier 4: Minor Information Friction (Penalty: 0.05)
    if row['price_t30'] is None and row['price_t5'] is not None:
        penalties += 0.05
        flags.append("TIER4_INSUFFICIENT_T30_HORIZON")
        
    dqs = max(0.0, round(1.0 - penalties, 2))
    
    if dqs >= 0.90:
        tier_cat = "TIER_A_PRISTINE"
    elif dqs >= 0.70:
        tier_cat = "TIER_B_USABLE"
    elif dqs >= 0.40:
        tier_cat = "TIER_C_DEGRADED"
    else:
        tier_cat = "TIER_D_UNRELIABLE"
        
    flag_str = " | ".join(flags) if flags else "CLEAN"
    return dqs, flag_str, tier_cat

res = [evaluate_tiered_dqs(row) for _, row in sample_df.iterrows()]
sample_df['dqs'] = [r[0] for r in res]
sample_df['flags'] = [r[1] for r in res]
sample_df['quality_tier'] = [r[2] for r in res]

print("\nKết quả phân bổ mức chất lượng dữ liệu (Data Quality Tier Distribution) trên 50,000 sự kiện:")
dist = sample_df['quality_tier'].value_counts()
for tier, cnt in dist.items():
    pct = cnt / len(sample_df) * 100
    print(f"  • {tier:22}: {cnt:>6,} sự kiện ({pct:5.2f}%)")

print("\nThống kê điểm số chất lượng Composite DQS:")
print(f"  • Điểm trung bình (Mean DQS): {sample_df['dqs'].mean():.3f}")
print(f"  • Trung vị (Median DQS)     : {sample_df['dqs'].median():.3f}")
print(f"  • Tỷ lệ đạt chuẩn huấn luyện (DQS >= 0.70): {(sample_df['dqs'] >= 0.70).mean()*100:.2f}%")
print(f"  • Tỷ lệ bị loại bỏ hoàn toàn (Tier 1 Reject): {(sample_df['quality_tier'] == 'TIER_1_REJECT').mean()*100:.2f}%")

top_flags = sample_df[sample_df['flags'] != 'CLEAN']['flags'].str.split(' \| ').explode().value_counts()
print("\nTop 5 khiếm khuyết phổ biến nhất được gắn cờ (Quality Defect Breakdown):")
for flag, count in top_flags.head(5).items():
    print(f"  - {flag:30}: {count:>6,} lần ({count/len(sample_df)*100:.2f}%)")

con.close()
print("\n" + "=" * 80)
print("HOÀN TẤT KHẢO SÁT THỰC NGHIỆM DEEP RESEARCH F101")
print("=" * 80)
