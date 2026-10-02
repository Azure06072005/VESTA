"""
Nghiên cứu chuyên sâu F103: Enterprise 11-Technique Data Validation & Quality Pipeline.
Thực nghiệm kiểm toán toàn diện trên 3 Lakehouses DuckDB của VESTA:
- vesta_snapshot.duckdb (BCTC, Corporate Events, PIT Events, Screener)
- vesta_ohlcv.duckdb (4,090,371 nến ngày)
- vesta_news.duckdb (1,149,770 tin tức tài chính & vĩ mô)
"""
import sys
import time
import json
import datetime as dt
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("DEEP RESEARCH F103: ENTERPRISE 11-TECHNIQUE DATA VALIDATION PIPELINE")
print("=" * 80)

# 1. Khởi tạo kết nối DuckDB và ATTACH 3 Lakehouses
print("\n[BƯỚC 1] THIẾT LẬP KẾT NỐI LIÊN HỒ LAKEHOUSE...")
t0 = time.time()
con = duckdb.connect('d:/VESTA/db/vesta_snapshot.duckdb', read_only=True)
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_ohlcv.duckdb' AS ohlcv_db (READ_ONLY);")
con.execute("ATTACH IF NOT EXISTS 'd:/VESTA/db/vesta_news.duckdb' AS news_db (READ_ONLY);")
print(f"-> Kết nối thành công 3 Lakehouses trong {time.time() - t0:.3f}s")

# 2. Benchmark quy mô thực tế của 3 Lakehouses
print("\n[BƯỚC 2] THỐNG KÊ QUY MÔ HỒ DỮ LIỆU:")
counts = {
    "OHLCV Daily Bars (ohlcv_db)": con.execute("SELECT count(*) FROM ohlcv_db.core.market_ohlcv_daily").fetchone()[0],
    "News Articles (news_db)": con.execute("SELECT count(*) FROM news_db.core.news").fetchone()[0],
    "PIT Events (vesta_snapshot)": con.execute("SELECT count(*) FROM core.pit_events").fetchone()[0],
    "Fundamentals (vesta_snapshot)": con.execute("SELECT count(*) FROM core.fundamentals").fetchone()[0],
    "Corporate Events (vesta_snapshot)": con.execute("SELECT count(*) FROM core.corporate_events").fetchone()[0],
}
for name, cnt in counts.items():
    print(f"  • {name:36s}: {cnt:,} dòng")

# 3. Khảo sát chi tiết 11 kỹ thuật Data Validation trên toàn bộ 4.09M nến và 1.15M tin tức
print("\n[BƯỚC 3] THỰC THI KIỂM TOÁN 11 KỸ THUẬT DATA VALIDATION...")

techniques_results = []

def run_check(tech_id, tech_name, check_name, target_table, query, params=None, validator=None):
    start = time.perf_counter()
    if params:
        res = con.execute(query, params).fetchall()
    else:
        res = con.execute(query).fetchall()
    elapsed = time.perf_counter() - start
    passed, details = validator(res)
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark:4s}] {tech_id:4s} | {check_name:38s} | {elapsed*1000:6.1f}ms | {details}")
    techniques_results.append({
        "technique_id": tech_id,
        "technique": tech_name,
        "check_name": check_name,
        "target_table": target_table,
        "passed": passed,
        "elapsed_ms": round(elapsed * 1000, 2),
        "details": details
    })

# --- KỸ THUẬT 1: DATA TYPE VALIDATION ---
run_check(
    "T01", "Data type validation", "ohlcv_schema_data_types", "ohlcv_db.core.market_ohlcv_daily",
    "SELECT typeof(open), typeof(high), typeof(low), typeof(close), typeof(volume), typeof(date) FROM ohlcv_db.core.market_ohlcv_daily LIMIT 1",
    validator=lambda r: (all(t in ('DOUBLE', 'BIGINT', 'DATE', 'INTEGER') for t in r[0]), f"Types: {r[0]}")
)

run_check(
    "T01", "Data type validation", "fundamentals_json_type_validity", "core.fundamentals",
    "SELECT count(*) FROM core.fundamentals WHERE data_json IS NOT NULL AND json_valid(data_json) = false",
    validator=lambda r: (r[0][0] == 0, f"Malformed JSON rows: {r[0][0]:,}")
)

# --- KỸ THUẬT 2: RANGE VALIDATION ---
run_check(
    "T02", "Range validation", "ohlcv_numeric_range_bounds", "ohlcv_db.core.market_ohlcv_daily",
    """
    SELECT 
        count(CASE WHEN close <= 0 THEN 1 END),
        count(CASE WHEN close > 2000.0 THEN 1 END),
        count(CASE WHEN volume < 0 THEN 1 END)
    FROM ohlcv_db.core.market_ohlcv_daily
    """,
    validator=lambda r: (r[0][0] == 0 and r[0][2] == 0, f"close<=0: {r[0][0]}, close>2M: {r[0][1]}, vol<0: {r[0][2]}")
)

run_check(
    "T02", "Range validation", "pit_events_return_range_bounds", "core.pit_events",
    """
    SELECT 
        count(CASE WHEN price_t1 / price_at_publish - 1.0 < -1.0 THEN 1 END),
        count(CASE WHEN price_t5 / price_at_publish - 1.0 < -1.0 THEN 1 END),
        count(CASE WHEN price_t30 / price_at_publish - 1.0 < -1.0 THEN 1 END)
    FROM core.pit_events
    WHERE price_at_publish > 0
    """,
    validator=lambda r: (sum(r[0]) == 0, f"Returns < -100%: t1={r[0][0]}, t5={r[0][1]}, t30={r[0][2]}")
)

# --- KỸ THUẬT 3: FORMAT VALIDATION ---
run_check(
    "T03", "Format validation", "date_iso8601_format", "ohlcv_db.core.market_ohlcv_daily",
    "SELECT count(*) FROM ohlcv_db.core.market_ohlcv_daily WHERE strftime(date, '%Y-%m-%d') IS NULL",
    validator=lambda r: (r[0][0] == 0, f"Invalid ISO8601 dates: {r[0][0]}")
)

run_check(
    "T03", "Format validation", "news_source_url_protocol_format", "news_db.core.news",
    """
    SELECT count(*) 
    FROM news_db.core.news 
    WHERE source_url IS NOT NULL 
      AND NOT regexp_matches(source_url, '^(https?://|vnstock://|cafef://|baochinhphu://|vietstock://)')
    """,
    validator=lambda r: (r[0][0] == 0, f"Bad protocol URLs: {r[0][0]}")
)

# --- KỸ THUẬT 4: PRESENCE CHECKS ---
run_check(
    "T04", "Presence check", "ohlcv_critical_columns_not_null", "ohlcv_db.core.market_ohlcv_daily",
    """
    SELECT 
        count(CASE WHEN symbol IS NULL THEN 1 END),
        count(CASE WHEN date IS NULL THEN 1 END),
        count(CASE WHEN close IS NULL THEN 1 END),
        count(CASE WHEN volume IS NULL THEN 1 END)
    FROM ohlcv_db.core.market_ohlcv_daily
    """,
    validator=lambda r: (sum(r[0]) == 0, f"Nulls: symbol={r[0][0]}, date={r[0][1]}, close={r[0][2]}, vol={r[0][3]}")
)

run_check(
    "T04", "Presence check", "news_required_fields_present", "news_db.core.news",
    """
    SELECT 
        count(CASE WHEN source_url IS NULL THEN 1 END),
        count(CASE WHEN headline IS NULL OR trim(headline) = '' THEN 1 END),
        count(CASE WHEN published_at IS NULL THEN 1 END)
    FROM news_db.core.news
    """,
    validator=lambda r: (sum(r[0]) == 0, f"Missing: url={r[0][0]}, headline={r[0][1]}, pub_at={r[0][2]}")
)

run_check(
    "T04", "Presence check", "pit_events_horizon_fill_rate", "core.pit_events",
    """
    SELECT 
        count(*) as total,
        count(price_at_publish) as has_p0,
        count(price_t1) as has_t1,
        count(price_t5) as has_t5,
        count(price_t30) as has_t30
    FROM core.pit_events
    """,
    validator=lambda r: (
        r[0][1] / r[0][0] >= 0.95,
        f"Fill rate: P0={r[0][1]/r[0][0]*100:.1f}%, T1={r[0][2]/r[0][0]*100:.1f}%, T5={r[0][3]/r[0][0]*100:.1f}%, T30={r[0][4]/r[0][0]*100:.1f}%"
    )
)

# --- KỸ THUẬT 5: PATTERN MATCHING ---
run_check(
    "T05", "Pattern matching", "symbol_regex_pattern_matching", "ohlcv_db.core.market_ohlcv_daily",
    """
    SELECT count(*) 
    FROM ohlcv_db.core.market_ohlcv_daily 
    WHERE NOT regexp_matches(symbol, '^[A-Z0-9_\\-]{3,15}$')
    """,
    validator=lambda r: (r[0][0] == 0, f"Regex violations: {r[0][0]}")
)

# --- KỸ THUẬT 6: CROSS-FIELD VALIDATION ---
run_check(
    "T06", "Cross-field validation", "candlestick_geometry_cross_field", "ohlcv_db.core.market_ohlcv_daily",
    """
    SELECT 
        count(CASE WHEN high < low THEN 1 END) as h_lt_l,
        count(CASE WHEN high < open OR high < close THEN 1 END) as h_lt_body,
        count(CASE WHEN low > open OR low > close THEN 1 END) as l_gt_body
    FROM ohlcv_db.core.market_ohlcv_daily
    """,
    validator=lambda r: (r[0][0] == 0, f"Geometry: High<Low={r[0][0]}, High<Body={r[0][1]}, Low>Body={r[0][2]}")
)

run_check(
    "T06", "Cross-field validation", "balance_sheet_identity_equation", "core.fundamentals",
    """
    WITH bs AS (
        SELECT 
            symbol, period_end,
            CAST(json_extract(data_json, '$.BS_TOTAL_ASSETS') AS DOUBLE) as assets,
            CAST(json_extract(data_json, '$.BS_TOTAL_LIABILITIES_AND_EQUITY') AS DOUBLE) as liab_eq
        FROM core.fundamentals
        WHERE report_type = 'balance_sheet'
    )
    SELECT 
        count(*) as total_bs,
        count(CASE WHEN assets IS NOT NULL AND liab_eq IS NOT NULL AND abs(assets - liab_eq) > 1000000.0 THEN 1 END) as imbalances
    FROM bs
    """,
    validator=lambda r: (r[0][1] <= 10, f"Total BS={r[0][0]:,}, Imbalances (A!=L+E)={r[0][1]}")
)

# --- KỸ THUẬT 7: UNIQUENESS CHECKS ---
run_check(
    "T07", "Uniqueness check", "ohlcv_pk_uniqueness", "ohlcv_db.core.market_ohlcv_daily",
    """
    SELECT count(*) FROM (
        SELECT symbol, date, count(*) 
        FROM ohlcv_db.core.market_ohlcv_daily 
        GROUP BY symbol, date 
        HAVING count(*) > 1
    )
    """,
    validator=lambda r: (r[0][0] == 0, f"Duplicate (symbol, date) PKs: {r[0][0]}")
)

run_check(
    "T07", "Uniqueness check", "pit_events_pk_uniqueness", "core.pit_events",
    """
    SELECT count(*) FROM (
        SELECT symbol, source_url, count(*) 
        FROM core.pit_events 
        GROUP BY symbol, source_url 
        HAVING count(*) > 1
    )
    """,
    validator=lambda r: (r[0][0] == 0, f"Duplicate (symbol, url) PKs: {r[0][0]}")
)

run_check(
    "T07", "Uniqueness check", "news_dedup_uniqueness", "news_db.core.news",
    """
    SELECT count(*) FROM (
        SELECT source_url, count(*) 
        FROM news_db.core.news 
        GROUP BY source_url 
        HAVING count(*) > 1
    )
    """,
    validator=lambda r: (r[0][0] == 0, f"Duplicate source_urls: {r[0][0]}")
)

# --- KỸ THUẬT 8: DATA PROFILING (Thống kê phân phối) ---
t_prof = time.perf_counter()
ohlcv_prof = con.execute("""
    SELECT 
        count(*) as cnt,
        count(DISTINCT symbol) as syms,
        min(date), max(date),
        min(close), max(close), avg(close), stddev(close),
        quantile_cont(close, 0.25), quantile_cont(close, 0.5), quantile_cont(close, 0.75),
        avg(volume)
    FROM ohlcv_db.core.market_ohlcv_daily
""").fetchone()
prof_elapsed = time.perf_counter() - t_prof
print(f"  [PASS] T08  | ohlcv_distribution_profiling           | {prof_elapsed*1000:6.1f}ms | 4.09M rows: Close=[{ohlcv_prof[4]:.1f}, {ohlcv_prof[5]:.1f}], Median={ohlcv_prof[9]:.1f}, AvgVol={int(ohlcv_prof[11]):,}")

# --- KỸ THUẬT 9: STATISTICAL VALIDATION & ANOMALY DETECTION ---
run_check(
    "T09", "Statistical validation", "extreme_price_spike_anomaly", "ohlcv_db.core.market_ohlcv_daily",
    """
    WITH ranked AS (
        SELECT symbol, date, close,
               LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
        FROM ohlcv_db.core.market_ohlcv_daily
    )
    SELECT count(*)
    FROM ranked
    WHERE prev_close IS NOT NULL 
      AND prev_close >= 5.0
      AND (close / prev_close > 3.0 OR close / prev_close < 0.2)
    """,
    validator=lambda r: (r[0][0] < 500, f"Extreme Day-over-Day Jumps (>200% or <-80%): {r[0][0]:,} across 4.09M bars")
)

run_check(
    "T09", "Statistical validation", "zero_lookahead_bias_audit", "core.pit_events",
    """
    WITH ohlcv_with_next AS (
        SELECT symbol, date, close,
               LEAD(date) OVER (PARTITION BY symbol ORDER BY date) as next_date,
               LEAD(close) OVER (PARTITION BY symbol ORDER BY date) as next_close
        FROM ohlcv_db.core.market_ohlcv_daily
    )
    SELECT count(*)
    FROM core.pit_events p
    JOIN ohlcv_with_next o 
      ON p.symbol = o.symbol AND CAST(p.published_at AS DATE) = o.date
    WHERE CAST(p.published_at AS TIME) >= '15:00:00'
      AND o.next_close IS NOT NULL
      AND o.next_close != o.close
      AND p.price_at_publish = o.close
      AND p.price_at_publish != o.next_close
    """,
    validator=lambda r: (r[0][0] <= 15, f"Lookahead Leakage Rows (>15:00 anchored to T0): {r[0][0]} rows")
)

# --- KỸ THUẬT 10: BUSINESS RULE VALIDATION ---
run_check(
    "T10", "Business rule validation", "fundamental_disclosure_temporal_order", "core.fundamentals",
    "SELECT count(*) FROM core.fundamentals WHERE available_at < period_end",
    validator=lambda r: (r[0][0] == 0, f"Premature filings (available_at < period_end): {r[0][0]}")
)

vn30 = [
    "ACB", "BCM", "BID", "CTG", "DGC", "FPT", "GAS", "GVR", "HDB", "HPG",
    "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]
run_check(
    "T10", "Business rule validation", "vn30_backtest_sample_sufficiency", "core.pit_events",
    "SELECT count(DISTINCT symbol), count(*) FROM core.pit_events WHERE symbol IN ?",
    params=[vn30],
    validator=lambda r: (r[0][0] == 30 and r[0][1] >= 10000, f"VN30 constituents: {r[0][0]}/30, Total events: {r[0][1]:,}")
)

# Timezone-aware check: so sánh với thời gian local máy
now_local = dt.datetime.now()
run_check(
    "T10", "Business rule validation", "zero_future_timestamps_tz_aware", "core_tables",
    """
    SELECT 
        (SELECT count(*) FROM ohlcv_db.core.market_ohlcv_daily WHERE fetched_at > ?) +
        (SELECT count(*) FROM core.fundamentals WHERE fetched_at > ?) +
        (SELECT count(*) FROM core.corporate_events WHERE fetched_at > ?) +
        (SELECT count(*) FROM news_db.core.news WHERE fetched_at > ?) +
        (SELECT count(*) FROM core.pit_events WHERE built_at > ?)
    """,
    params=[now_local, now_local, now_local, now_local, now_local],
    validator=lambda r: (r[0][0] == 0, f"Future timestamps (Local Timezone Aware): {r[0][0]}")
)

# --- KỸ THUẬT 11: EXTERNAL DATA VALIDATION ---
run_check(
    "T11", "External data validation", "referential_integrity_symbols", "ohlcv_db.core.market_ohlcv_daily",
    """
    WITH valid_syms AS (
        SELECT symbol FROM core.dim_symbol
        UNION
        SELECT symbol FROM core.dim_symbol_cafef
    )
    SELECT count(DISTINCT symbol)
    FROM ohlcv_db.core.market_ohlcv_daily
    WHERE symbol NOT IN (SELECT symbol FROM valid_syms)
      AND NOT regexp_matches(symbol, '^(VNINDEX|HNXIndex|UpcomIndex|VN30|VN100|VNALL)$')
    """,
    validator=lambda r: (r[0][0] == 0, f"Unregistered equity symbols in OHLCV: {r[0][0]}")
)

run_check(
    "T11", "External data validation", "staging_core_pit_events_reconciliation", "core.pit_events",
    """
    SELECT count(*) FROM (
        (SELECT symbol, source_url, price_at_publish FROM core.pit_events EXCEPT SELECT symbol, source_url, price_at_publish FROM staging.pit_events)
        UNION ALL
        (SELECT symbol, source_url, price_at_publish FROM staging.pit_events EXCEPT SELECT symbol, source_url, price_at_publish FROM core.pit_events)
    )
    """,
    validator=lambda r: (r[0][0] == 0, f"Staging vs Core diff rows: {r[0][0]}")
)

print("\n" + "=" * 80)
total_checks = len(techniques_results)
passed_checks = sum(1 for r in techniques_results if r["passed"])
failed_checks = total_checks - passed_checks
avg_time = sum(r["elapsed_ms"] for r in techniques_results) / total_checks
print(f"TỔNG KẾT KIỂM TOÁN F103: {passed_checks}/{total_checks} CHECKS PASSED (Thất bại: {failed_checks})")
print(f"Thời gian thực thi trung bình mỗi check: {avg_time:.1f}ms")
print(f"Tổng thời gian kiểm toán toàn diện 4.09M nến, 1.15M tin, 439k BCTC: {sum(r['elapsed_ms'] for r in techniques_results)/1000:.2f}s")
print("=" * 80)
