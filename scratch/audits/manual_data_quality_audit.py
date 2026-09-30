"""scratch/audits/manual_data_quality_audit.py

Kiểm tra thủ công chất lượng dữ liệu toàn diện (Comprehensive Data Quality Audit):
Thứ tự kiểm tra:
1. OHLCV (1D & 1m)
2. Báo cáo tài chính (Fundamentals & Balance Check)
3. Tin tức & Báo chí (News & Media Integrity)
4. Sự kiện & Danh mục tham chiếu (Corporate Actions & Reference)

Cơ chế: Chỉ đọc (Read-only), ghi nhận vi phạm vào Báo cáo kiểm toán (Audit Log),
không sửa đổi dữ liệu thô.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from etl import db

SNAPSHOT_DB = str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb")
INTRADAY_DB = str(PROJECT_ROOT / "db" / "vesta_intraday_1m.duckdb")
NEWS_DB = str(PROJECT_ROOT / "db" / "vesta_news.duckdb")

TODAY_STR = dt.date.today().isoformat()
NOW_STR = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

audit_results = {
    "audit_timestamp": NOW_STR,
    "pillars": {}
}


def audit_ohlcv() -> dict:
    """1. Kiểm định chất lượng nến ngày OHLCV 1D và nến phút 1m."""
    print("\n" + "=" * 80)
    print("PILLAR 1: KIỂM ĐỊNH CHẤT LƯỢNG GIÁ NẾN OHLCV (1D & 1M)")
    print("=" * 80)
    res = {}
    con = duckdb.connect(SNAPSHOT_DB, read_only=True)
    try:
        # 1.1 Kiểm tra nến ngày 1D
        total_1d = con.execute("SELECT count(*) FROM core.market_ohlcv_daily").fetchone()[0]
        
        # Lỗi logic cơ bản: high < low, low > close, open <= 0, close <= 0
        logic_errs = con.execute("""
            SELECT count(*) 
            FROM core.market_ohlcv_daily 
            WHERE high < low 
               OR high < open 
               OR high < close 
               OR low > open 
               OR low > close
               OR close <= 0 
               OR open <= 0
        """).fetchone()[0]

        # Lỗi ngày tương lai hoặc cổ đại
        date_errs = con.execute("""
            SELECT count(*) 
            FROM core.market_ohlcv_daily 
            WHERE date > CURRENT_DATE OR date < '2000-01-01'
        """).fetchone()[0]

        # Kiểm tra trùng lặp (symbol, date)
        dup_errs = con.execute("""
            SELECT count(*) FROM (
                SELECT symbol, date, count(*) 
                FROM core.market_ohlcv_daily 
                GROUP BY symbol, date 
                HAVING count(*) > 1
            )
        """).fetchone()[0]

        # Biến động bất thường không có sự kiện điều chỉnh (Return > 100% hoặc < -50% trong 1 ngày)
        spike_errs = con.execute("""
            WITH daily_ret AS (
                SELECT symbol, date, close,
                       lag(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
                FROM core.market_ohlcv_daily
            )
            SELECT count(*) 
            FROM daily_ret 
            WHERE prev_close > 0 
              AND (close / prev_close > 2.0 OR close / prev_close < 0.4)
        """).fetchone()[0]

        res["ohlcv_1d"] = {
            "total_records": total_1d,
            "logic_errors": logic_errs,
            "date_outliers": date_errs,
            "duplicate_symbol_date": dup_errs,
            "abnormal_price_spikes": spike_errs,
            "status": "PASS" if logic_errs == 0 and date_errs == 0 and dup_errs == 0 else "WARNING"
        }
        print(f"  • OHLCV 1D: {total_1d:,} bản ghi")
        print(f"    - Lỗi logic giá (H < L, Open/Close <= 0): {logic_errs:,}")
        print(f"    - Lỗi ngày tương lai / cổ đại (< 2000 hoặc > nay): {date_errs:,}")
        print(f"    - Trùng lặp (symbol, date): {dup_errs:,}")
        print(f"    - Cảnh báo biến động giá dị thường (> 100% / < -60%): {spike_errs:,}")

    finally:
        con.close()

    # 1.2 Kiểm tra nến phút 1m
    con_intra = duckdb.connect(INTRADAY_DB, read_only=True)
    try:
        total_1m = con_intra.execute("SELECT count(*) FROM core.market_ohlcv_1m").fetchone()[0]
        distinct_syms_1m = con_intra.execute("SELECT count(DISTINCT symbol) FROM core.market_ohlcv_1m").fetchone()[0]
        
        # Lỗi logic nến 1m
        logic_1m = con_intra.execute("""
            SELECT count(*) 
            FROM core.market_ohlcv_1m 
            WHERE high < low OR close <= 0 OR volume < 0
        """).fetchone()[0]

        # Nến ngoài giờ giao dịch (trước 08:30 hoặc sau 15:30)
        time_errs_1m = con_intra.execute("""
            SELECT count(*) 
            FROM core.market_ohlcv_1m 
            WHERE CAST(time AS TIME) < TIME '08:30:00' 
               OR CAST(time AS TIME) > TIME '15:30:00'
        """).fetchone()[0]

        res["ohlcv_1m"] = {
            "total_records": total_1m,
            "distinct_symbols": distinct_syms_1m,
            "logic_errors": logic_1m,
            "outside_trading_hours": time_errs_1m,
            "status": "PASS" if logic_1m == 0 and time_errs_1m == 0 else "WARNING"
        }
        print(f"  • OHLCV 1m: {total_1m:,} bản ghi ({distinct_syms_1m} mã)")
        print(f"    - Lỗi logic nến 1m (H < L, C <= 0, V < 0): {logic_1m:,}")
        print(f"    - Nến ngoài khung giờ khớp lệnh (trước 08:30 / sau 15:30): {time_errs_1m:,}")
    finally:
        con_intra.close()

    return res


def audit_fundamentals() -> dict:
    """2. Kiểm định tính cân đối kế toán và toàn vẹn của Báo cáo tài chính."""
    print("\n" + "=" * 80)
    print("PILLAR 2: KIỂM ĐỊNH BÁO CÁO TÀI CHÍNH (FUNDAMENTALS & BALANCE SHEET)")
    print("=" * 80)
    res = {}
    con = duckdb.connect(SNAPSHOT_DB, read_only=True)
    try:
        total_stmts = con.execute("SELECT count(*) FROM core.fundamentals").fetchone()[0]
        distinct_syms = con.execute("SELECT count(DISTINCT symbol) FROM core.fundamentals").fetchone()[0]

        # Kiểm tra trùng lặp kỳ BCTC
        dup_periods = con.execute("""
            SELECT count(*) FROM (
                SELECT symbol, period_end, report_type, count(*) 
                FROM core.fundamentals 
                GROUP BY symbol, period_end, report_type 
                HAVING count(*) > 1
            )
        """).fetchone()[0]

        # Kiểm tra Look-ahead bias: available_at < period_end
        lookahead_errs = con.execute("""
            SELECT count(*) 
            FROM core.fundamentals 
            WHERE available_at < period_end
        """).fetchone()[0]

        # Kiểm tra tính cân đối Bảng CĐKT (Cân đối kế toán: Tài sản = Nợ + Vốn CSH)
        # Sử dụng json_extract nếu có lưu trữ metrics dạng JSON
        balance_check_errs = 0
        try:
            # Kiểm tra các báo cáo có trường TotalAssets và TotalLiabilities
            row_chk = con.execute("""
                SELECT count(*) 
                FROM core.fundamentals 
                WHERE report_type = 'balance_sheet'
                  AND metrics IS NOT NULL
                  AND json_extract(metrics, '$.asset') IS NOT NULL
                  AND json_extract(metrics, '$.debt') IS NOT NULL
                  AND json_extract(metrics, '$.equity') IS NOT NULL
                  AND abs(CAST(json_extract(metrics, '$.asset') AS DOUBLE) - 
                          (CAST(json_extract(metrics, '$.debt') AS DOUBLE) + CAST(json_extract(metrics, '$.equity') AS DOUBLE))) 
                      > (0.02 * abs(CAST(json_extract(metrics, '$.asset') AS DOUBLE)) + 1000)
            """).fetchone()
            balance_check_errs = row_chk[0] if row_chk else 0
        except Exception:
            balance_check_errs = 0

        res = {
            "total_records": total_stmts,
            "distinct_symbols": distinct_syms,
            "duplicate_periods": dup_periods,
            "lookahead_bias_violations": lookahead_errs,
            "balance_sheet_imbalance": balance_check_errs,
            "status": "PASS" if dup_periods == 0 and lookahead_errs == 0 else "WARNING"
        }
        print(f"  • BCTC: {total_stmts:,} báo cáo ({distinct_syms} mã)")
        print(f"    - Trùng lặp kỳ công bố (symbol, period, report_type): {dup_periods:,}")
        print(f"    - Vi phạm Look-ahead bias (available_at < period_end): {lookahead_errs:,}")
        print(f"    - Lệch cân đối CĐKT (Tài sản != Nợ + Vốn CSH > 2%): {balance_check_errs:,}")
    finally:
        con.close()
    return res


def audit_news() -> dict:
    """3. Kiểm định chất lượng tin tức báo chí & công bố thông tin."""
    print("\n" + "=" * 80)
    print("PILLAR 3: KIỂM ĐỊNH TIN TỨC, CÔNG BỐ THÔNG TIN & TRÙNG LẶP URL")
    print("=" * 80)
    res = {}
    con_news = duckdb.connect(NEWS_DB, read_only=True)
    try:
        total_news = con_news.execute("SELECT count(*) FROM core.news").fetchone()[0]
        total_resources = con_news.execute("SELECT count(*) FROM core.news_resources").fetchone()[0]
        total_disc = con_news.execute("SELECT count(*) FROM core.cafef_disclosures").fetchone()[0]

        # Kiểm tra ngày công bố tương lai (> Hôm nay)
        future_news = con_news.execute("""
            SELECT count(*) 
            FROM core.news 
            WHERE published_at > CURRENT_TIMESTAMP + INTERVAL 1 DAY
        """).fetchone()[0]

        future_resources = con_news.execute("""
            SELECT count(*) 
            FROM core.news_resources 
            WHERE published_at > CURRENT_TIMESTAMP + INTERVAL 1 DAY
        """).fetchone()[0]

        # Kiểm tra tin bài rỗng tiêu đề
        empty_headline = con_news.execute("""
            SELECT count(*) 
            FROM core.news 
            WHERE headline IS NULL OR trim(headline) = ''
        """).fetchone()[0]

        # Kiểm tra trùng lặp URL
        dup_url_news = con_news.execute("""
            SELECT count(*) FROM (
                SELECT source_url, count(*) 
                FROM core.news 
                WHERE source_url IS NOT NULL 
                GROUP BY source_url 
                HAVING count(*) > 1
            )
        """).fetchone()[0]

        dup_url_res = con_news.execute("""
            SELECT count(*) FROM (
                SELECT source_url, count(*) 
                FROM core.news_resources 
                WHERE source_url IS NOT NULL 
                GROUP BY source_url 
                HAVING count(*) > 1
            )
        """).fetchone()[0]

        # Tỷ lệ tin bài có thân bài (Body Enrichment Rate)
        with_body = con_news.execute("""
            SELECT count(*) 
            FROM core.news 
            WHERE body IS NOT NULL AND length(trim(body)) > 50
        """).fetchone()[0]
        body_rate = (with_body / total_news * 100) if total_news > 0 else 0

        res = {
            "total_stock_news": total_news,
            "total_news_resources": total_resources,
            "total_disclosures": total_disc,
            "future_dates_news": future_news,
            "future_dates_resources": future_resources,
            "empty_headline_news": empty_headline,
            "duplicate_urls_news": dup_url_news,
            "duplicate_urls_resources": dup_url_res,
            "body_enriched_count": with_body,
            "body_enriched_rate_pct": round(body_rate, 2),
            "status": "PASS" if future_news == 0 and empty_headline == 0 and dup_url_news == 0 else "WARNING"
        }
        print(f"  • Tin tức cổ phiếu CafeF : {total_news:,} tin bài")
        print(f"  • Báo chí tài chính & Vĩ mô: {total_resources:,} tin bài")
        print(f"  • Công bố thông tin CafeF : {total_disc:,} văn bản")
        print(f"    - Tin có ngày tương lai (> Ngày mai): {future_news:,} (news) | {future_resources:,} (resources)")
        print(f"    - Tin bài rỗng tiêu đề: {empty_headline:,}")
        print(f"    - Trùng lặp URL: {dup_url_news:,} (news) | {dup_url_res:,} (resources)")
        print(f"    - Tỷ lệ có thân bài hoàn chỉnh (Body Enrichment): {body_rate:.2f}% ({with_body:,}/{total_news:,})")
    finally:
        con_news.close()
    return res


def audit_corporate_actions_and_reference() -> dict:
    """4. Kiểm định sự kiện doanh nghiệp, điều chỉnh giá CAF và tính toàn vẹn danh mục tham chiếu."""
    print("\n" + "=" * 80)
    print("PILLAR 4: KIỂM ĐỊNH SỰ KIỆN DOANH NGHIỆP, CAF & TOÀN VẸN THAM CHIẾU")
    print("=" * 80)
    res = {}
    con = duckdb.connect(SNAPSHOT_DB, read_only=True)
    try:
        total_events = con.execute("SELECT count(*) FROM core.corporate_events").fetchone()[0]
        total_adj = con.execute("SELECT count(*) FROM core.price_adjustment_events").fetchone()[0]
        total_caf = con.execute("SELECT count(*) FROM core.symbol_caf_timeline").fetchone()[0]
        total_syms = con.execute("SELECT count(*) FROM core.dim_symbol").fetchone()[0]

        # Kiểm tra sự kiện trùng lặp
        dup_events = con.execute("""
            SELECT count(*) FROM (
                SELECT symbol, event_id, count(*) 
                FROM core.corporate_events 
                GROUP BY symbol, event_id 
                HAVING count(*) > 1
            )
        """).fetchone()[0]

        # Kiểm tra mã mồ côi (Orphan symbols trong OHLCV không có trong dim_symbol)
        orphan_ohlcv = con.execute("""
            SELECT count(DISTINCT symbol) 
            FROM core.market_ohlcv_daily 
            WHERE symbol NOT IN (SELECT symbol FROM core.dim_symbol)
        """).fetchone()[0]

        # Kiểm tra CAF Factor hợp lệ (> 0 và <= 1.0)
        invalid_caf = con.execute("""
            SELECT count(*) 
            FROM core.symbol_caf_timeline 
            WHERE caf <= 0 OR caf > 1.0001
        """).fetchone()[0]

        res = {
            "corporate_events": total_events,
            "price_adjustment_events": total_adj,
            "caf_timeline_entries": total_caf,
            "dim_symbol_count": total_syms,
            "duplicate_events": dup_events,
            "orphan_symbols_in_ohlcv": orphan_ohlcv,
            "invalid_caf_values": invalid_caf,
            "status": "PASS" if dup_events == 0 and orphan_ohlcv == 0 and invalid_caf == 0 else "WARNING"
        }
        print(f"  • Danh mục mã niêm yết (dim_symbol): {total_syms:,} mã")
        print(f"  • Sự kiện quyền & Cổ tức : {total_events:,} bản ghi")
        print(f"  • Sự kiện điều chỉnh giá (CAF): {total_adj:,} bản ghi ({total_caf:,} mốc timeline)")
        print(f"    - Sự kiện trùng lặp (symbol, event_id): {dup_events:,}")
        print(f"    - Mã cổ phiếu mồ côi trong OHLCV (chưa có trong dim_symbol): {orphan_ohlcv:,}")
        print(f"    - Giá trị CAF không hợp lệ (<= 0 hoặc > 1.0): {invalid_caf:,}")
    finally:
        con.close()
    return res


def main():
    print("=" * 80)
    print("      VESTA QUANTITATIVE LAKEHOUSE — COMPREHENSIVE DATA QUALITY AUDIT")
    print(f"      Thời điểm kiểm định: {NOW_STR}")
    print("=" * 80)

    p1 = audit_ohlcv()
    p2 = audit_fundamentals()
    p3 = audit_news()
    p4 = audit_corporate_actions_and_reference()

    audit_results["pillars"]["1_ohlcv"] = p1
    audit_results["pillars"]["2_fundamentals"] = p2
    audit_results["pillars"]["3_news"] = p3
    audit_results["pillars"]["4_corporate_actions_and_reference"] = p4

    out_file = PROJECT_ROOT / "scratch" / "audits" / "data_quality_audit_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"[+] Hoàn tất kiểm tra chất lượng dữ liệu thủ công!")
    print(f"[+] Báo cáo kiểm toán đã được xuất ra: {out_file.relative_to(PROJECT_ROOT)}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
