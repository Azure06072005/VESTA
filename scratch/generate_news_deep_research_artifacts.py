import duckdb
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import json
import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def run_deep_research():
    con = duckdb.connect("db/vesta_news.duckdb", read_only=True)
    
    # 1. Phân loại 4 chiều mục tiêu bằng Vectorized Regex
    con.execute("""
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
    """)
    
    # Lấy bảng xếp hạng tổng hợp
    df_src = con.execute("""
        SELECT 
            source,
            count(*) as total_articles,
            sum(is_symbol_relevant) as sym_cnt,
            round(sum(is_symbol_relevant)*100.0/count(*), 2) as sym_density_pct,
            sum(is_market_relevant) as mkt_cnt,
            round(sum(is_market_relevant)*100.0/count(*), 2) as mkt_density_pct,
            sum(is_economy_relevant) as eco_cnt,
            round(sum(is_economy_relevant)*100.0/count(*), 2) as eco_density_pct,
            sum(is_global_relevant) as glo_cnt,
            round(sum(is_global_relevant)*100.0/count(*), 2) as glo_density_pct
        FROM news_categorized
        GROUP BY source
        HAVING total_articles >= 200
        ORDER BY total_articles DESC
    """).fetchdf()
    
    df_news_type = con.execute("""
        SELECT 
            news_type,
            count(*) as total_articles,
            sum(is_symbol_relevant) as sym_cnt,
            round(sum(is_symbol_relevant)*100.0/count(*), 2) as sym_density_pct,
            sum(is_market_relevant) as mkt_cnt,
            round(sum(is_market_relevant)*100.0/count(*), 2) as mkt_density_pct,
            sum(is_economy_relevant) as eco_cnt,
            round(sum(is_economy_relevant)*100.0/count(*), 2) as eco_density_pct,
            sum(is_global_relevant) as glo_cnt,
            round(sum(is_global_relevant)*100.0/count(*), 2) as glo_density_pct
        FROM news_categorized
        GROUP BY news_type
        ORDER BY total_articles DESC
    """).fetchdf()

    df_doc_type = con.execute("""
        SELECT 
            doc_type,
            count(*) as total_articles,
            sum(is_symbol_relevant) as sym_cnt,
            round(sum(is_symbol_relevant)*100.0/count(*), 2) as sym_density_pct,
            sum(is_market_relevant) as mkt_cnt,
            round(sum(is_market_relevant)*100.0/count(*), 2) as mkt_density_pct,
            sum(is_economy_relevant) as eco_cnt,
            round(sum(is_economy_relevant)*100.0/count(*), 2) as eco_density_pct,
            sum(is_global_relevant) as glo_cnt,
            round(sum(is_global_relevant)*100.0/count(*), 2) as glo_density_pct
        FROM news_categorized
        GROUP BY doc_type
        HAVING total_articles >= 1000
        ORDER BY total_articles DESC
        LIMIT 15
    """).fetchdf()

    # Tạo biểu đồ trực quan hóa đa chiều
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    plt.suptitle("XẾP HẠNG NGUỒN TIN THEO 4 PHÂN KHÚC MỤC TIÊU (1,149,304 BÀI VIẾT)", fontsize=16, fontweight='bold', y=0.98)
    
    # 1. Symbols
    top_sym = df_src.sort_values(by='sym_cnt', ascending=False).head(8)
    sns.barplot(data=top_sym, x='sym_cnt', y='source', palette='Blues_r', ax=axes[0, 0])
    axes[0, 0].set_title("1. Tin Tức Mã Cổ Phiếu / Doanh Nghiệp (SYMBOLS)", fontweight='bold')
    axes[0, 0].set_xlabel("Số lượng bài viết")
    axes[0, 0].set_ylabel("")
    for i, row in enumerate(top_sym.itertuples()):
        axes[0, 0].text(row.sym_cnt + 5000, i, f"{int(row.sym_cnt):,} ({row.sym_density_pct}%)", va='center', fontsize=9)
    axes[0, 0].set_xlim(0, top_sym['sym_cnt'].max() * 1.25)
    
    # 2. Financial Market
    top_mkt = df_src.sort_values(by='mkt_cnt', ascending=False).head(8)
    sns.barplot(data=top_mkt, x='mkt_cnt', y='source', palette='Oranges_r', ax=axes[0, 1])
    axes[0, 1].set_title("2. Thị Trường Tài Chính, TTCK & Dòng Tiền (FINANCIAL MARKET)", fontweight='bold')
    axes[0, 1].set_xlabel("Số lượng bài viết")
    axes[0, 1].set_ylabel("")
    for i, row in enumerate(top_mkt.itertuples()):
        axes[0, 1].text(row.mkt_cnt + 500, i, f"{int(row.mkt_cnt):,} ({row.mkt_density_pct}%)", va='center', fontsize=9)
    axes[0, 1].set_xlim(0, top_mkt['mkt_cnt'].max() * 1.25)

    # 3. Economy & Macro
    top_eco = df_src.sort_values(by='eco_cnt', ascending=False).head(8)
    sns.barplot(data=top_eco, x='eco_cnt', y='source', palette='Greens_r', ax=axes[1, 0])
    axes[1, 0].set_title("3. Kinh Tế Vĩ Mô & Chính Sách Điều Hành (ECONOMY)", fontweight='bold')
    axes[1, 0].set_xlabel("Số lượng bài viết")
    axes[1, 0].set_ylabel("")
    for i, row in enumerate(top_eco.itertuples()):
        axes[1, 0].text(row.eco_cnt + 1000, i, f"{int(row.eco_cnt):,} ({row.eco_density_pct}%)", va='center', fontsize=9)
    axes[1, 0].set_xlim(0, top_eco['eco_cnt'].max() * 1.25)

    # 4. Global Affection
    top_glo = df_src.sort_values(by='glo_cnt', ascending=False).head(8)
    sns.barplot(data=top_glo, x='glo_cnt', y='source', palette='Purples_r', ax=axes[1, 1])
    axes[1, 1].set_title("4. Tác Động Toàn Cầu, Fed & Địa Chính Trị (GLOBAL AFFECTION)", fontweight='bold')
    axes[1, 1].set_xlabel("Số lượng bài viết")
    axes[1, 1].set_ylabel("")
    for i, row in enumerate(top_glo.itertuples()):
        axes[1, 1].text(row.glo_cnt + 200, i, f"{int(row.glo_cnt):,} ({row.glo_density_pct}%)", va='center', fontsize=9)
    axes[1, 1].set_xlim(0, top_glo['glo_cnt'].max() * 1.25)

    plt.tight_layout()
    chart_path = "notebooks/news/02_relevance_ranking_chart.png"
    plt.savefig(chart_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"📊 Đã xuất đồ họa xếp hạng tại: {chart_path}")

    # Xuất báo cáo JSON
    report_data = {
        "sources_ranking": df_src.to_dict(orient='records'),
        "news_type_ranking": df_news_type.to_dict(orient='records'),
        "doc_type_ranking": df_doc_type.to_dict(orient='records')
    }
    with open("scratch/news_relevance_ranking_report.json", "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print("📁 Đã lưu báo cáo định lượng tại: scratch/news_relevance_ranking_report.json")
    
    con.close()

if __name__ == '__main__':
    run_deep_research()
