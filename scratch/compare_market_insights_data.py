"""Audit and comparison script for F007b Market Insights & Macro data in DuckDB."""
import sys
import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def audit_f007b_data():
    con = duckdb.connect("db/vesta_snapshot.duckdb", read_only=True)

    print("=" * 80)
    print("AUDIT BÁO CÁO DỮ LIỆU F007b (MARKET INSIGHTS, SCREENER, VALUATION, MACRO)")
    print("=" * 80)

    # 1. Screener Snapshot
    print("\n[1] core.market_screener_snapshot (Bộ lọc định lượng toàn thị trường):")
    total_screener = con.execute("SELECT count(*) FROM core.market_screener_snapshot").fetchone()[0]
    ex_dist = con.execute("""
        SELECT exchange, count(*) as cnt 
        FROM core.market_screener_snapshot 
        GROUP BY exchange 
        ORDER BY cnt DESC
    """).fetchall()
    print(f"    - Tổng số mã cổ phiếu: {total_screener:,}")
    print(f"    - Phân bổ theo sàn: {dict(ex_dist)}")
    
    sample_screener = con.execute("""
        SELECT symbol, exchange, price, reference_price, ceiling_price, floor_price, price_change_percent, market_cap, stock_strength
        FROM core.market_screener_snapshot
        WHERE symbol IN ('FPT', 'VNM', 'HPG', 'TCB', 'SSI')
        ORDER BY symbol
    """).df()
    print("    - Mẫu dữ liệu các cổ phiếu trụ (VN30):")
    print(sample_screener.to_string(index=False))

    # 2. Index Valuation Series
    print("\n[2] core.index_valuation_series (Chuỗi định giá chỉ số lịch sử P/E, P/B):")
    total_val = con.execute("SELECT count(*) FROM core.index_valuation_series").fetchone()[0]
    val_breakdown = con.execute("""
        SELECT index_code, ratio_code, count(*) as count, min(report_date) as start_date, max(report_date) as end_date,
               round(avg(ratio_value), 2) as avg_val, round(min(ratio_value), 2) as min_val, round(max(ratio_value), 2) as max_val
        FROM core.index_valuation_series
        GROUP BY index_code, ratio_code
        ORDER BY index_code, ratio_code
    """).df()
    print(f"    - Tổng số phiên định giá lịch sử: {total_val:,}")
    print(val_breakdown.to_string(index=False))

    # 3. Market Breadth Series
    print("\n[3] core.market_breadth_series (Chuỗi độ rộng thị trường lịch sử):")
    total_breadth = con.execute("SELECT count(*) FROM core.market_breadth_series").fetchone()[0]
    breadth_breakdown = con.execute("""
        SELECT exchange, count(*) as count, min(trade_date) as start_date, max(trade_date) as end_date,
               round(avg(above_ma50_pct), 2) as avg_above_ma50, round(avg(pe), 2) as avg_pe
        FROM core.market_breadth_series
        GROUP BY exchange
        ORDER BY exchange
    """).df()
    print(f"    - Tổng số ngày độ rộng thị trường: {total_breadth:,}")
    print(breadth_breakdown.to_string(index=False))

    # 4. Market Sentiment Snapshot
    print("\n[4] core.market_sentiment_snapshot (Chỉ số Sợ hãi & Tham lam Fear & Greed):")
    sent_df = con.execute("""
        SELECT exchange, snapshot_date, fear_greed_score, advances, declines, no_change, mfi, rsi
        FROM core.market_sentiment_snapshot
        ORDER BY exchange
    """).df()
    print(sent_df.to_string(index=False))

    # 5. Macroeconomic Series
    print("\n[5] core.macro_economic_series & core.macro_rates (Chỉ số Kinh tế vĩ mô dài hạn):")
    macro_cnt = con.execute("SELECT count(*) FROM core.macro_economic_series").fetchone()[0]
    rates_cnt = con.execute("SELECT count(*) FROM core.macro_rates").fetchone()[0]
    print(f"    - Tổng số bản ghi vĩ mô (core.macro_economic_series): {macro_cnt:,}")
    print(f"    - Tổng số bản ghi lãi suất (core.macro_rates): {rates_cnt:,}")

    macro_dist = con.execute("""
        SELECT indicator, count(*) as cnt, min(period_date) as min_date, max(period_date) as max_date
        FROM core.macro_economic_series
        GROUP BY indicator
        ORDER BY cnt DESC
    """).df()
    print(macro_dist.to_string(index=False))

    con.close()
    print("\n" + "=" * 80)
    print("HOÀN TẤT AUDIT BÁO CÁO!")
    print("=" * 80)

if __name__ == "__main__":
    audit_f007b_data()
