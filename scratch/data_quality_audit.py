"""Comprehensive Data Quality Audit Script for VESTA Database.

Evaluates the 6 Key Dimensions of Data Quality across F001 -> F009 tables:
1. Accuracy (Price validity, High>=Low, Volume>=0, Financial balance checks)
2. Completeness / Null Checks (Critical NOT NULL fields)
3. Consistency & Referential Integrity (Orphan checks vs dim_symbol)
4. Timeliness & Zero Look-Ahead Bias (No future timestamps, available_at >= period_end)
5. Uniqueness (Primary key duplicates, duplicate rates)
6. Validity & Schema Validation (Formats, regex, valid enum ranges)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import duckdb
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "d:/VESTA/db/vesta.duckdb"

def run_quality_audit() -> dict:
    con = duckdb.connect(DB_PATH, read_only=True)
    report = {
        "audit_timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database": DB_PATH,
        "results": {}
    }

    print("================================================================================")
    print("           VESTA COMPREHENSIVE DATA QUALITY AUDIT (F001 -> F009)                ")
    print("================================================================================\n")

    # -------------------------------------------------------------------------
    # DIMENSION 1: COMPLETENESS & NULL CHECKS
    # -------------------------------------------------------------------------
    print("--- [1] DIMENSION: COMPLETENESS & NULL CHECKS ---")
    null_checks = {}

    # 1.1 OHLCV
    ohlcv_nulls = con.execute("""
        SELECT 
            count(*) as total,
            sum(CASE WHEN symbol IS NULL THEN 1 ELSE 0 END) as null_sym,
            sum(CASE WHEN date IS NULL THEN 1 ELSE 0 END) as null_date,
            sum(CASE WHEN open IS NULL THEN 1 ELSE 0 END) as null_open,
            sum(CASE WHEN high IS NULL THEN 1 ELSE 0 END) as null_high,
            sum(CASE WHEN low IS NULL THEN 1 ELSE 0 END) as null_low,
            sum(CASE WHEN close IS NULL THEN 1 ELSE 0 END) as null_close,
            sum(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) as null_vol,
            sum(CASE WHEN fetched_at IS NULL THEN 1 ELSE 0 END) as null_fetch
        FROM core.market_ohlcv_daily
    """).fetchone()
    null_checks["market_ohlcv_daily"] = {
        "total": ohlcv_nulls[0],
        "null_symbol": ohlcv_nulls[1],
        "null_date": ohlcv_nulls[2],
        "null_open": ohlcv_nulls[3],
        "null_high": ohlcv_nulls[4],
        "null_low": ohlcv_nulls[5],
        "null_close": ohlcv_nulls[6],
        "null_volume": ohlcv_nulls[7],
        "null_fetched_at": ohlcv_nulls[8],
    }
    print(f"  [market_ohlcv_daily] Total: {ohlcv_nulls[0]:,} | Null Symbol: {ohlcv_nulls[1]} | Null Date: {ohlcv_nulls[2]} | Null Price: {ohlcv_nulls[6]}")

    # 1.2 Fundamentals
    fund_nulls = con.execute("""
        SELECT 
            count(*) as total,
            sum(CASE WHEN symbol IS NULL THEN 1 ELSE 0 END) as null_sym,
            sum(CASE WHEN report_type IS NULL THEN 1 ELSE 0 END) as null_rtype,
            sum(CASE WHEN period_end IS NULL THEN 1 ELSE 0 END) as null_period,
            sum(CASE WHEN available_at IS NULL THEN 1 ELSE 0 END) as null_avail,
            sum(CASE WHEN data_json IS NULL OR length(trim(data_json)) = 0 THEN 1 ELSE 0 END) as empty_data,
            sum(CASE WHEN fetched_at IS NULL THEN 1 ELSE 0 END) as null_fetch
        FROM core.fundamentals
    """).fetchone()
    null_checks["fundamentals"] = {
        "total": fund_nulls[0],
        "null_symbol": fund_nulls[1],
        "null_report_type": fund_nulls[2],
        "null_period_end": fund_nulls[3],
        "null_available_at": fund_nulls[4],
        "empty_data_json": fund_nulls[5],
        "null_fetched_at": fund_nulls[6],
    }
    print(f"  [fundamentals] Total: {fund_nulls[0]:,} | Null Symbol: {fund_nulls[1]} | Empty Data JSON: {fund_nulls[5]}")

    # 1.3 News
    news_nulls = con.execute("""
        SELECT 
            count(*) as total,
            sum(CASE WHEN symbol IS NULL THEN 1 ELSE 0 END) as null_sym,
            sum(CASE WHEN published_at IS NULL THEN 1 ELSE 0 END) as null_pub,
            sum(CASE WHEN headline IS NULL OR length(trim(headline)) = 0 THEN 1 ELSE 0 END) as empty_headline,
            sum(CASE WHEN source_url IS NULL OR length(trim(source_url)) = 0 THEN 1 ELSE 0 END) as empty_url,
            sum(CASE WHEN available_at IS NULL THEN 1 ELSE 0 END) as null_avail,
            sum(CASE WHEN body IS NULL OR length(trim(body)) = 0 THEN 1 ELSE 0 END) as empty_body
        FROM core.news
    """).fetchone()
    null_checks["news"] = {
        "total": news_nulls[0],
        "null_symbol": news_nulls[1],
        "null_published_at": news_nulls[2],
        "empty_headline": news_nulls[3],
        "empty_source_url": news_nulls[4],
        "null_available_at": news_nulls[5],
        "empty_body": news_nulls[6],
    }
    print(f"  [news] Total: {news_nulls[0]:,} | Null Symbol: {news_nulls[1]} | Empty Headline: {news_nulls[3]} | Empty Body: {news_nulls[6]:,} ({news_nulls[6]/news_nulls[0]*100:.1f}%)")

    # 1.4 Macro Policy
    macro_nulls = con.execute("""
        SELECT 
            count(*) as total,
            sum(CASE WHEN source IS NULL THEN 1 ELSE 0 END) as null_src,
            sum(CASE WHEN published_at IS NULL THEN 1 ELSE 0 END) as null_pub,
            sum(CASE WHEN headline IS NULL OR length(trim(headline)) = 0 THEN 1 ELSE 0 END) as empty_headline,
            sum(CASE WHEN source_url IS NULL OR length(trim(source_url)) = 0 THEN 1 ELSE 0 END) as empty_url,
            sum(CASE WHEN body IS NULL OR length(trim(body)) = 0 THEN 1 ELSE 0 END) as empty_body
        FROM core.macro_policy
    """).fetchone()
    null_checks["macro_policy"] = {
        "total": macro_nulls[0],
        "null_source": macro_nulls[1],
        "null_published_at": macro_nulls[2],
        "empty_headline": macro_nulls[3],
        "empty_source_url": macro_nulls[4],
        "empty_body": macro_nulls[5],
    }
    print(f"  [macro_policy] Total: {macro_nulls[0]:,} | Empty Headline: {macro_nulls[3]} | Empty Body: {macro_nulls[5]:,}")
    report["results"]["null_checks"] = null_checks

    # -------------------------------------------------------------------------
    # DIMENSION 2: UNIQUENESS & DEDUPLICATION CHECKS
    # -------------------------------------------------------------------------
    print("\n--- [2] DIMENSION: UNIQUENESS CHECKS ---")
    uniqueness_checks = {}

    # 2.1 dim_symbol uniqueness
    dim_dups = con.execute("""
        SELECT count(*) - count(distinct symbol) FROM core.dim_symbol
    """).fetchone()[0]
    print(f"  [dim_symbol] Duplicate symbols: {dim_dups}")
    uniqueness_checks["dim_symbol_duplicates"] = dim_dups

    # 2.2 market_ohlcv_daily uniqueness on (symbol, date)
    ohlcv_dups = con.execute("""
        SELECT count(*) FROM (
            SELECT symbol, date, count(*) as cnt 
            FROM core.market_ohlcv_daily 
            GROUP BY symbol, date 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  [market_ohlcv_daily] Duplicate (symbol, date) pairs: {ohlcv_dups}")
    uniqueness_checks["market_ohlcv_duplicates"] = ohlcv_dups

    # 2.3 market_index_daily uniqueness on (index_code, date)
    idx_dups = con.execute("""
        SELECT count(*) FROM (
            SELECT index_code, date, count(*) as cnt 
            FROM core.market_index_daily 
            GROUP BY index_code, date 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  [market_index_daily] Duplicate (index_code, date) pairs: {idx_dups}")
    uniqueness_checks["market_index_duplicates"] = idx_dups

    # 2.4 news uniqueness on source_url
    news_url_dups = con.execute("""
        SELECT count(*) FROM (
            SELECT source_url, count(*) as cnt 
            FROM core.news 
            GROUP BY source_url 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  [news] Duplicate source_url: {news_url_dups}")
    uniqueness_checks["news_url_duplicates"] = news_url_dups

    # 2.5 macro_policy uniqueness on source_url
    macro_dups = con.execute("""
        SELECT count(*) FROM (
            SELECT source_url, count(*) as cnt 
            FROM core.macro_policy 
            GROUP BY source_url 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  [macro_policy] Duplicate source_url: {macro_dups}")
    uniqueness_checks["macro_url_duplicates"] = macro_dups

    # 2.6 fundamentals uniqueness on (symbol, report_type, period_end, fetched_at)
    fund_dups = con.execute("""
        SELECT count(*) FROM (
            SELECT symbol, report_type, period_end, fetched_at, count(*) as cnt 
            FROM core.fundamentals 
            GROUP BY symbol, report_type, period_end, fetched_at 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  [fundamentals] Duplicate (symbol, report_type, period_end, fetched_at): {fund_dups}")
    uniqueness_checks["fundamentals_duplicates"] = fund_dups

    # 2.7 stock_research_reports uniqueness on report_url
    report_dups = con.execute("""
        SELECT count(*) FROM (
            SELECT report_url, count(*) as cnt 
            FROM core.stock_research_reports 
            GROUP BY report_url 
            HAVING count(*) > 1
        )
    """).fetchone()[0]
    print(f"  [stock_research_reports] Duplicate report_url: {report_dups}")
    uniqueness_checks["stock_reports_duplicates"] = report_dups
    report["results"]["uniqueness_checks"] = uniqueness_checks

    # -------------------------------------------------------------------------
    # DIMENSION 3: ACCURACY & NUMERICAL BOUNDS
    # -------------------------------------------------------------------------
    print("\n--- [3] DIMENSION: ACCURACY & NUMERICAL INTEGRITY ---")
    accuracy_checks = {}

    # 3.1 OHLCV logic: High >= Low, High >= Open, High >= Close, Close >= Low, Volume >= 0
    ohlcv_invalid = con.execute("""
        SELECT 
            sum(CASE WHEN high < low THEN 1 ELSE 0 END) as high_lt_low,
            sum(CASE WHEN high < open THEN 1 ELSE 0 END) as high_lt_open,
            sum(CASE WHEN high < close THEN 1 ELSE 0 END) as high_lt_close,
            sum(CASE WHEN low > open THEN 1 ELSE 0 END) as low_gt_open,
            sum(CASE WHEN low > close THEN 1 ELSE 0 END) as low_gt_close,
            sum(CASE WHEN volume < 0 THEN 1 ELSE 0 END) as neg_volume,
            sum(CASE WHEN close <= 0 THEN 1 ELSE 0 END) as non_pos_close
        FROM core.market_ohlcv_daily
    """).fetchone()
    accuracy_checks["ohlcv_anomalies"] = {
        "high_less_than_low": ohlcv_invalid[0],
        "high_less_than_open": ohlcv_invalid[1],
        "high_less_than_close": ohlcv_invalid[2],
        "low_greater_than_open": ohlcv_invalid[3],
        "low_greater_than_close": ohlcv_invalid[4],
        "negative_volume": ohlcv_invalid[5],
        "non_positive_close": ohlcv_invalid[6],
    }
    print(f"  [OHLCV Bounds] High < Low: {ohlcv_invalid[0]} | High < Open/Close: {ohlcv_invalid[1]}/{ohlcv_invalid[2]} | Negative Vol: {ohlcv_invalid[5]} | Close <= 0: {ohlcv_invalid[6]}")

    # 3.2 Index logic: High >= Low, Close > 0
    idx_invalid = con.execute("""
        SELECT 
            sum(CASE WHEN high < low THEN 1 ELSE 0 END) as high_lt_low,
            sum(CASE WHEN close <= 0 THEN 1 ELSE 0 END) as non_pos_close
        FROM core.market_index_daily
    """).fetchone()
    accuracy_checks["index_anomalies"] = {
        "high_less_than_low": idx_invalid[0],
        "non_positive_close": idx_invalid[1],
    }
    print(f"  [Index Bounds] High < Low: {idx_invalid[0]} | Close <= 0: {idx_invalid[1]}")

    # 3.3 Research Reports: target_price > 0, upside_pct within realistic bounds (-90% to +1000%)
    reports_anom = con.execute("""
        SELECT 
            sum(CASE WHEN target_price IS NOT NULL AND target_price <= 0 THEN 1 ELSE 0 END) as neg_target,
            sum(CASE WHEN upside_pct IS NOT NULL AND (upside_pct < -90 OR upside_pct > 1000) THEN 1 ELSE 0 END) as extreme_upside
        FROM core.stock_research_reports
    """).fetchone()
    accuracy_checks["research_reports_anomalies"] = {
        "negative_target_price": reports_anom[0],
        "extreme_upside_outliers": reports_anom[1],
    }
    print(f"  [Research Reports] Target Price <= 0: {reports_anom[0]} | Extreme Upside (>1000% / <-90%): {reports_anom[1]}")
    report["results"]["accuracy_checks"] = accuracy_checks

    # -------------------------------------------------------------------------
    # DIMENSION 4: CONSISTENCY & REFERENTIAL INTEGRITY
    # -------------------------------------------------------------------------
    print("\n--- [4] DIMENSION: REFERENTIAL INTEGRITY (ORPHAN CHECKS) ---")
    ref_checks = {}

    # 4.1 OHLCV symbols vs dim_symbol (active 3-letter tickers)
    ohlcv_orphans = con.execute("""
        SELECT count(distinct o.symbol)
        FROM core.market_ohlcv_daily o
        LEFT JOIN core.dim_symbol s ON o.symbol = s.symbol
        WHERE s.symbol IS NULL AND length(o.symbol) = 3
    """).fetchone()[0]
    print(f"  [market_ohlcv_daily] 3-letter symbols not in dim_symbol (potential historical delisted): {ohlcv_orphans}")
    ref_checks["ohlcv_3letter_orphans"] = ohlcv_orphans

    # 4.2 Fundamentals symbols vs dim_symbol
    fund_orphans = con.execute("""
        SELECT count(distinct f.symbol)
        FROM core.fundamentals f
        LEFT JOIN core.dim_symbol s ON f.symbol = s.symbol
        WHERE s.symbol IS NULL
    """).fetchone()[0]
    print(f"  [fundamentals] Symbols not in dim_symbol: {fund_orphans}")
    ref_checks["fundamentals_orphans"] = fund_orphans

    # 4.3 Corporate Events symbols vs dim_symbol
    event_orphans = con.execute("""
        SELECT count(distinct e.symbol)
        FROM core.corporate_events e
        LEFT JOIN core.dim_symbol s ON e.symbol = s.symbol
        WHERE s.symbol IS NULL
    """).fetchone()[0]
    print(f"  [corporate_events] Symbols not in dim_symbol: {event_orphans}")
    ref_checks["corporate_events_orphans"] = event_orphans

    # 4.4 Stock Research Reports symbols vs dim_symbol
    report_orphans = con.execute("""
        SELECT count(distinct r.symbol)
        FROM core.stock_research_reports r
        LEFT JOIN core.dim_symbol s ON r.symbol = s.symbol
        WHERE r.symbol IS NOT NULL AND s.symbol IS NULL
    """).fetchone()[0]
    print(f"  [stock_research_reports] Symbols not in dim_symbol: {report_orphans}")
    ref_checks["stock_reports_orphans"] = report_orphans

    # 4.5 News symbols vs dim_symbol
    news_orphans = con.execute("""
        SELECT count(distinct n.symbol)
        FROM core.news n
        LEFT JOIN core.dim_symbol s ON n.symbol = s.symbol
        WHERE s.symbol IS NULL AND n.symbol != 'VNINDEX'
    """).fetchone()[0]
    print(f"  [news] Symbols not in dim_symbol (excluding VNINDEX): {news_orphans}")
    ref_checks["news_orphans"] = news_orphans
    report["results"]["referential_integrity"] = ref_checks

    # -------------------------------------------------------------------------
    # DIMENSION 5: TIMELINESS & ZERO LOOK-AHEAD BIAS
    # -------------------------------------------------------------------------
    print("\n--- [5] DIMENSION: TIMELINESS & ZERO LOOK-AHEAD BIAS ---")
    timeliness_checks = {}

    now_utc = dt.datetime.now(dt.timezone.utc)

    # 5.1 No future timestamps in fetched_at or published_at
    future_records = con.execute(f"""
        SELECT 
            (SELECT count(*) FROM core.market_ohlcv_daily WHERE date > CURRENT_DATE),
            (SELECT count(*) FROM core.market_ohlcv_daily WHERE fetched_at > CURRENT_TIMESTAMP + INTERVAL 1 DAY),
            (SELECT count(*) FROM core.news WHERE published_at > CURRENT_TIMESTAMP + INTERVAL 1 DAY),
            (SELECT count(*) FROM core.macro_policy WHERE published_at > CURRENT_TIMESTAMP + INTERVAL 1 DAY),
            (SELECT count(*) FROM core.fundamentals WHERE fetched_at > CURRENT_TIMESTAMP + INTERVAL 1 DAY)
    """).fetchone()
    timeliness_checks["future_timestamps"] = {
        "future_ohlcv_date": future_records[0],
        "future_ohlcv_fetched_at": future_records[1],
        "future_news_published_at": future_records[2],
        "future_macro_published_at": future_records[3],
        "future_fundamentals_fetched_at": future_records[4],
    }
    print(f"  [Future Timestamps] OHLCV Date: {future_records[0]} | OHLCV Fetch: {future_records[1]} | News Pub: {future_records[2]} | Fund Fetch: {future_records[4]}")

    # 5.2 Zero Look-Ahead Bias: news available_at >= published_at
    news_lag_violation = con.execute("""
        SELECT count(*) FROM core.news WHERE available_at < published_at
    """).fetchone()[0]
    print(f"  [News Look-Ahead Check] available_at < published_at violations: {news_lag_violation}")
    timeliness_checks["news_lookahead_violations"] = news_lag_violation

    # 5.3 Zero Look-Ahead Bias: fundamentals available_at >= period_end + 30 days
    fund_lag_violation = con.execute("""
        SELECT count(*) FROM core.fundamentals WHERE available_at < period_end + INTERVAL 30 DAY
    """).fetchone()[0]
    print(f"  [Fundamentals Look-Ahead Check] available_at < period_end + 30 days: {fund_lag_violation}")
    timeliness_checks["fundamentals_lookahead_violations"] = fund_lag_violation

    # 5.4 Freshness range: Min Date -> Max Date per table
    date_ranges = {
        "market_ohlcv_daily": con.execute("SELECT min(date), max(date) FROM core.market_ohlcv_daily").fetchone(),
        "market_index_daily": con.execute("SELECT min(date), max(date) FROM core.market_index_daily").fetchone(),
        "news": con.execute("SELECT min(published_at), max(published_at) FROM core.news").fetchone(),
        "fundamentals": con.execute("SELECT min(period_end), max(period_end) FROM core.fundamentals").fetchone(),
        "macro_policy": con.execute("SELECT min(published_at), max(published_at) FROM core.macro_policy").fetchone(),
        "corporate_events": con.execute("SELECT min(event_date), max(event_date) FROM core.corporate_events WHERE event_date IS NOT NULL").fetchone(),
    }
    timeliness_checks["coverage_date_ranges"] = {
        k: (str(v[0]), str(v[1])) for k, v in date_ranges.items()
    }
    print("\n  [Dataset Coverage Ranges]")
    for k, (d_min, d_max) in timeliness_checks["coverage_date_ranges"].items():
        print(f"    - {k:25s}: {d_min}  -->  {d_max}")
    report["results"]["timeliness_checks"] = timeliness_checks

    # -------------------------------------------------------------------------
    # DIMENSION 6: VALIDITY & FORMAT VALIDATION
    # -------------------------------------------------------------------------
    print("\n--- [6] DIMENSION: VALIDITY & FORMAT VALIDATION ---")
    validity_checks = {}

    # 6.1 Valid report_type in core.fundamentals
    valid_rtypes = {'balance_sheet', 'income_statement', 'cash_flow', 'ratio'}
    found_rtypes = set(r[0] for r in con.execute("SELECT DISTINCT report_type FROM core.fundamentals").fetchall())
    invalid_rtypes = found_rtypes - valid_rtypes
    print(f"  [fundamentals.report_type] Found: {found_rtypes} | Invalid: {invalid_rtypes}")
    validity_checks["fundamentals_invalid_report_types"] = list(invalid_rtypes)

    # 6.2 Valid event_type in core.corporate_events
    found_etypes = [r[0] for r in con.execute("SELECT event_type, count(*) FROM core.corporate_events GROUP BY event_type").fetchall()]
    print(f"  [corporate_events.event_type] Categories: {found_etypes}")
    validity_checks["corporate_event_types"] = found_etypes

    # 6.3 Valid URL protocol format (http:// or https://)
    invalid_news_urls = con.execute("""
        SELECT count(*) FROM core.news WHERE source_url NOT LIKE 'http://%' AND source_url NOT LIKE 'https://%'
    """).fetchone()[0]
    invalid_macro_urls = con.execute("""
        SELECT count(*) FROM core.macro_policy WHERE source_url NOT LIKE 'http://%' AND source_url NOT LIKE 'https://%'
    """).fetchone()[0]
    print(f"  [URL Validity] Invalid News URLs: {invalid_news_urls} | Invalid Macro URLs: {invalid_macro_urls}")
    validity_checks["invalid_news_urls"] = invalid_news_urls
    validity_checks["invalid_macro_urls"] = invalid_macro_urls
    report["results"]["validity_checks"] = validity_checks

    con.close()

    # Save full report to out/
    os.makedirs("d:/VESTA/out", exist_ok=True)
    out_file = "d:/VESTA/out/data_quality_audit_f001_f009.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Detailed audit report saved to: {out_file}")

    print("\n================================================================================")
    print("                    DATA QUALITY AUDIT EVALUATION FINISHED                     ")
    print("================================================================================")
    return report

if __name__ == "__main__":
    run_quality_audit()
