import duckdb
import pandas as pd
import numpy as np
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def analyze_relevance():
    t0 = time.time()
    con = duckdb.connect("db/vesta_news.duckdb", read_only=True)
    
    print("=== ĐANG QUÉT TOÀN BỘ 1,149,304 BÀI VIẾT TRONG VESTA NEWS LAKEHOUSE ===")
    
    # Định nghĩa các biểu thức regex phân loại 4 phân khúc
    # 1. Symbols: có mã symbol hoặc nhắc tới mã chứng khoán trong headline
    # 2. Financial Market: TTCK, thanh khoản, chỉ số, VNINDEX, phái sinh, khối ngoại
    # 3. Economy & Macro: vĩ mô, GDP, CPI, chính sách, nghị định, thông tư, NHNN, đầu tư công
    # 4. Global Affection: thế giới, Fed, Wall Street, Mỹ, DXY, giá dầu, địa chính trị, xung đột, toàn cầu
    
    query = """
    CREATE OR REPLACE TEMPORARY TABLE news_categorized AS
    SELECT 
        source_url,
        source,
        news_type,
        COALESCE(doc_type, 'UNSPECIFIED') as doc_type,
        symbol,
        published_at,
        headline,
        
        -- Domain 1: Symbols / Equities
        (symbol IS NOT NULL 
         OR regexp_matches(lower(headline), '(cổ phiếu [a-z0-9]{3}|mã [a-z0-9]{3}|bctc|đhcđ|hđqt|chia cổ tức|lợi nhuận sau thuế|doanh thu thuần|thâu tóm|m&a)'))::INT as is_symbol_relevant,
        
        -- Domain 2: Financial Market
        (regexp_matches(lower(headline), '(vn-index|vnindex|vn30|chứng khoán|thanh khoản|khối ngoại|tự doanh|khớp lệnh|sàn hose|sàn hnx|upcom|bán ròng|mua ròng|chỉ số|trái phiếu|phái sinh|lãi suất liên ngân hàng|thị trường tiền tệ|room ngoại)'))::INT as is_market_relevant,
        
        -- Domain 3: Economy & Macro Policy
        (regexp_matches(lower(headline), '(kinh tế|vĩ mô|gdp|lạm phát|cpi|ngân sách|thuế|xuất khẩu|nhập khẩu|fdi|đầu tư công|nghị định|thông tư|nghị quyết|thủ tướng|chính phủ|ngân hàng nhà nước|sbv|tín dụng|hạn mức|chính sách tài khóa|chính sách tiền tệ)'))::INT as is_economy_relevant,
        
        -- Domain 4: Global Affection
        (regexp_matches(lower(headline), '(thế giới|toàn cầu|fed |cục dự trữ liên bang|wall street|dow jones|s&p 500|nasdaq|dxy|usd|trung quốc|châu âu|eu|nhật bản|địa chính trị|giá dầu|dầu thô|brent|wti|vàng thế giới|xung đột|chiến sự|thuế quan|thương mại toàn cầu|kinh tế mỹ)'))::INT as is_global_relevant
    FROM core.news;
    """
    con.execute(query)
    
    total_scanned = con.execute("SELECT count(*) FROM news_categorized").fetchone()[0]
    print(f"✅ Đã phân loại xong {total_scanned:,} bài viết trong {time.time() - t0:.2f} giây.")
    
    # 1. Thống kê tổng quan 4 phân khúc
    overview = con.execute("""
        SELECT 
            sum(is_symbol_relevant) as symbols_count,
            round(sum(is_symbol_relevant) * 100.0 / count(*), 2) as symbols_pct,
            
            sum(is_market_relevant) as market_count,
            round(sum(is_market_relevant) * 100.0 / count(*), 2) as market_pct,
            
            sum(is_economy_relevant) as economy_count,
            round(sum(is_economy_relevant) * 100.0 / count(*), 2) as economy_pct,
            
            sum(is_global_relevant) as global_count,
            round(sum(is_global_relevant) * 100.0 / count(*), 2) as global_pct
        FROM news_categorized
    """).fetchdf()
    print("\n=== TỔNG QUAN ĐỘ PHỦ 4 PHÂN KHÚC MỤC TIÊU ===")
    print(overview.to_string(index=False))
    
    # 2. Xếp hạng Top Nguồn Tin (source) theo từng phân khúc
    print("\n=== TOP NGUỒN TIN PHÙ HỢP NHẤT CHO MÃ CỔ PHIẾU (SYMBOLS) ===")
    rank_src_sym = con.execute("""
        SELECT 
            source, 
            count(*) as total_articles,
            sum(is_symbol_relevant) as symbol_articles,
            round(sum(is_symbol_relevant) * 100.0 / count(*), 2) as relevance_rate_pct,
            round(sum(is_symbol_relevant) * 100.0 / (SELECT sum(is_symbol_relevant) FROM news_categorized), 2) as market_share_pct
        FROM news_categorized
        GROUP BY source
        HAVING total_articles >= 100
        ORDER BY symbol_articles DESC
        LIMIT 10
    """).fetchdf()
    print(rank_src_sym.to_string(index=False))
    
    print("\n=== TOP NGUỒN TIN PHÙ HỢP NHẤT CHO THỊ TRƯỜNG TÀI CHÍNH (FINANCIAL MARKET) ===")
    rank_src_mkt = con.execute("""
        SELECT 
            source, 
            count(*) as total_articles,
            sum(is_market_relevant) as market_articles,
            round(sum(is_market_relevant) * 100.0 / count(*), 2) as relevance_rate_pct,
            round(sum(is_market_relevant) * 100.0 / (SELECT sum(is_market_relevant) FROM news_categorized), 2) as market_share_pct
        FROM news_categorized
        GROUP BY source
        HAVING total_articles >= 100
        ORDER BY market_articles DESC
        LIMIT 10
    """).fetchdf()
    print(rank_src_mkt.to_string(index=False))
    
    print("\n=== TOP NGUỒN TIN PHÙ HỢP NHẤT CHO KINH TẾ & CHÍNH SÁCH VĨ MÔ (ECONOMY) ===")
    rank_src_eco = con.execute("""
        SELECT 
            source, 
            count(*) as total_articles,
            sum(is_economy_relevant) as economy_articles,
            round(sum(is_economy_relevant) * 100.0 / count(*), 2) as relevance_rate_pct,
            round(sum(is_economy_relevant) * 100.0 / (SELECT sum(is_economy_relevant) FROM news_categorized), 2) as market_share_pct
        FROM news_categorized
        GROUP BY source
        HAVING total_articles >= 100
        ORDER BY economy_articles DESC
        LIMIT 10
    """).fetchdf()
    print(rank_src_eco.to_string(index=False))
    
    print("\n=== TOP NGUỒN TIN PHÙ HỢP NHẤT CHO TÁC ĐỘNG TOÀN CẦU (GLOBAL AFFECTION) ===")
    rank_src_glo = con.execute("""
        SELECT 
            source, 
            count(*) as total_articles,
            sum(is_global_relevant) as global_articles,
            round(sum(is_global_relevant) * 100.0 / count(*), 2) as relevance_rate_pct,
            round(sum(is_global_relevant) * 100.0 / (SELECT sum(is_global_relevant) FROM news_categorized), 2) as market_share_pct
        FROM news_categorized
        GROUP BY source
        HAVING total_articles >= 100
        ORDER BY global_articles DESC
        LIMIT 10
    """).fetchdf()
    print(rank_src_glo.to_string(index=False))
    
    # 3. Xếp hạng theo NEWS_TYPE
    print("\n=== XẾP HẠNG THEO NEWS_TYPE ĐỐI VỚI 4 PHÂN KHÚC ===")
    rank_news_type = con.execute("""
        SELECT 
            news_type,
            count(*) as total_articles,
            sum(is_symbol_relevant) as symbols,
            round(sum(is_symbol_relevant)*100.0/count(*), 1) as sym_pct,
            sum(is_market_relevant) as market,
            round(sum(is_market_relevant)*100.0/count(*), 1) as mkt_pct,
            sum(is_economy_relevant) as economy,
            round(sum(is_economy_relevant)*100.0/count(*), 1) as eco_pct,
            sum(is_global_relevant) as global,
            round(sum(is_global_relevant)*100.0/count(*), 1) as glo_pct
        FROM news_categorized
        GROUP BY news_type
        ORDER BY total_articles DESC
    """).fetchdf()
    print(rank_news_type.to_string(index=False))
    
    # 4. Xếp hạng theo DOC_TYPE
    print("\n=== TOP 15 DOC_TYPE THEO TỪNG PHÂN KHÚC ===")
    rank_doc_type = con.execute("""
        SELECT 
            doc_type,
            count(*) as total_articles,
            sum(is_symbol_relevant) as sym_cnt,
            sum(is_market_relevant) as mkt_cnt,
            sum(is_economy_relevant) as eco_cnt,
            sum(is_global_relevant) as glo_cnt
        FROM news_categorized
        GROUP BY doc_type
        HAVING total_articles >= 500
        ORDER BY total_articles DESC
        LIMIT 15
    """).fetchdf()
    print(rank_doc_type.to_string(index=False))

    con.close()
    print(f"\n[HOÀN TẤT] Tổng thời gian phân tích: {time.time() - t0:.2f}s")

if __name__ == "__main__":
    analyze_relevance()
