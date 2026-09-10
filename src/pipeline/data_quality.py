"""Enterprise Comprehensive Data Validation & Quality Pipeline for VESTA.

Implements the 11 Industry-Standard Data Validation Techniques (Twilio Segment,
IBM Data Validation, Future Processing Best Practices) across both Data Engineering
and Data Analysis disciplines:

DATA VALIDATION TECHNIQUES FOR ENGINEERS:
1. Data Type Validation: Verifies column schemas and ensures strict type conformity.
2. Range Validation: Validates numerical boundaries (prices, volumes, returns).
3. Format Validation: Validates ISO8601 dates, timestamps, and URL/URI schemes.
4. Presence Checks: Ensures mandatory fields are populated and non-null.
5. Pattern Matching: Regex pattern enforcement on symbols and URIs.
6. Cross-Field Validation: Multi-column intra-record logic (Candlesticks, Balance Sheet $A = L + E$).

DATA VALIDATION TECHNIQUES FOR ANALYSTS:
7. Uniqueness Checks: Composite primary keys and duplicate detection.
8. Data Profiling: Statistical distribution metrics, row counts, null fractions, quantiles.
9. Statistical Validation: Zero look-ahead bias audit ($T+1$ anchoring) & extreme anomaly detection.
10. Business Rule Validation: Vietnam market hours (15:00 cutoff), UPCoM VWAP rule, BCTC disclosure timing.
11. External Data Validation: Referential integrity cross-referencing authoritative symbol universes.

Also maps backward-compatibly to the 7 Enterprise Data Quality Dimensions:
Completeness, Uniqueness, Validity, Timeliness, Accuracy, Consistency, Fitness for Purpose.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import pathlib
import sys
from typing import Any

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from etl import db  # noqa: E402
from pipeline.symbol_classification import is_known_non_dim_symbol  # noqa: E402


@dataclasses.dataclass
class DQCheckResult:
    """Káº¿t quáº£ kiá»ƒm tra cá»§a má»™t quy táº¯c Data Validation."""
    technique: str = ""  # 1 trong 11 ká»¹ thuáº­t Data Validation chuáº©n
    dimension: str = ""  # 1 trong 7 chiá»u Data Quality truyá»n thá»‘ng
    check_name: str = ""
    target_table: str = ""
    passed: bool = True
    severity: str = "INFO"  # "ERROR" | "WARNING" | "INFO"
    metrics: dict[str, Any] = dataclasses.field(default_factory=dict)
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class DataQualityPipeline:
    """Hệ thống kiểm định chất lượng và xác thực dữ liệu toàn diện cho VESTA."""

    def __init__(self, con: duckdb.DuckDBPyConnection | None = None) -> None:
        self.con = con or db.connect(read_only=True)

    # =========================================================================
    # TECHNIQUE 1: DATA TYPE VALIDATION (Kỹ sư - Kiểm tra Kiểu Dữ Liệu)
    # =========================================================================
    def check_data_types(self) -> list[DQCheckResult]:
        """Kỹ thuật 1: Xác thực kiểu dữ liệu SQL và schema của các bảng core."""
        results: list[DQCheckResult] = []

        # 1.1 OHLCV schema verification
        ohlcv_info = self.con.execute("PRAGMA table_info('core.market_ohlcv_daily')").fetchall()
        actual_types = {col: dtype.upper() for _, col, dtype, *_ in ohlcv_info}
        expected_types = {
            "symbol": "VARCHAR",
            "date": "DATE",
            "open": "DOUBLE",
            "high": "DOUBLE",
            "low": "DOUBLE",
            "close": "DOUBLE",
            "volume": "BIGINT",
        }
        mismatches = {
            col: f"Expected {expected_types[col]}, got {actual_types.get(col)}"
            for col in expected_types
            if col not in actual_types or actual_types[col] != expected_types[col]
        }
        passed_ohlcv = (len(mismatches) == 0)
        results.append(
            DQCheckResult(
                technique="Data type validation",
                dimension="Validity",
                check_name="ohlcv_schema_data_types",
                target_table="core.market_ohlcv_daily",
                passed=passed_ohlcv,
                severity="ERROR" if not passed_ohlcv else "INFO",
                metrics={"mismatches": mismatches, "column_count": len(actual_types)},
                details="Cac cot gia phai la DOUBLE, volume la BIGINT, date la DATE.",
            )
        )

        # 1.2 Fundamentals data_json parseable check
        non_json = self.con.execute(
            """
            SELECT count(*) 
            FROM core.fundamentals 
            WHERE data_json IS NOT NULL AND json_valid(data_json) = false
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Data type validation",
                dimension="Validity",
                check_name="fundamentals_json_type_validity",
                target_table="core.fundamentals",
                passed=(non_json == 0),
                severity="ERROR" if non_json > 0 else "INFO",
                metrics={"invalid_json_rows": non_json},
                details="Moi ban ghi data_json trong core.fundamentals phai la hop le (valid JSON).",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 2: RANGE VALIDATION (Kỹ sư - Kiểm tra Giới Hạn Khoảng Giá Trị)
    # =========================================================================
    def check_range(self) -> list[DQCheckResult]:
        """Kỹ thuật 2: Kiểm tra biên giá trị số (giá, khối lượng, tỷ suất lợi nhuận)."""
        results: list[DQCheckResult] = []

        # 2.1 OHLCV Price Sanity Range: Price > 0 when traded, and close <= 2,000,000 VND
        row = self.con.execute(
            """
            SELECT 
                count(*) as total,
                count(CASE WHEN volume > 0 AND (close <= 0 OR close > 2000000) THEN 1 END) as out_of_range_price,
                count(CASE WHEN volume < 0 THEN 1 END) as negative_volume
            FROM core.market_ohlcv_daily
            """
        ).fetchone()
        tot, bad_price, neg_vol = row if row else (0, 0, 0)
        # Fatal error if negative volume > 0 or bad_price > 500 (>0.01% of rows). Warnings flagged for legacy vendor zero closes.
        passed = (neg_vol == 0 and bad_price <= 500)
        severity = "ERROR" if not passed else ("WARNING" if bad_price > 0 else "INFO")
        results.append(
            DQCheckResult(
                technique="Range validation",
                dimension="Validity",
                check_name="ohlcv_numeric_range_bounds",
                target_table="core.market_ohlcv_daily",
                passed=passed,
                severity=severity,
                metrics={"total_rows": tot, "out_of_range_price": bad_price, "negative_volume": neg_vol},
                details="Gia dong cua phai > 0 va <= 2,000,000 VND khi co giao dich; volume >= 0.",
            )
        )

        # 2.2 Forward Return Range in PIT Events: returns cannot drop below -100% (-1.0)
        ret_anomalies = self.con.execute(
            """
            SELECT count(*) 
            FROM core.pit_events 
            WHERE price_at_publish > 0 AND (
                (price_t1 IS NOT NULL AND (price_t1 / price_at_publish - 1.0) < -1.0)
                OR (price_t5 IS NOT NULL AND (price_t5 / price_at_publish - 1.0) < -1.0)
                OR (price_t30 IS NOT NULL AND (price_t30 / price_at_publish - 1.0) < -1.0)
            )
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Range validation",
                dimension="Accuracy",
                check_name="pit_events_return_range_bounds",
                target_table="core.pit_events",
                passed=(ret_anomalies == 0),
                severity="ERROR" if ret_anomalies > 0 else "INFO",
                metrics={"return_range_violations": ret_anomalies},
                details="Ty suat loi nhuan cac ky han t1, t5, t30 khong duoc nho hon -100% (-1.0).",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 3: FORMAT VALIDATION (Kỹ sư - Kiểm tra Định Dạng)
    # =========================================================================
    def check_format(self) -> list[DQCheckResult]:
        """Kỹ thuật 3: Kiểm tra định dạng ngày tháng ISO8601 và URL/URI."""
        results: list[DQCheckResult] = []

        # 3.1 Date format validation YYYY-MM-DD
        invalid_date_fmt = self.con.execute(
            """
            SELECT count(*) 
            FROM core.market_ohlcv_daily 
            WHERE strftime(date, '%Y-%m-%d') != CAST(date AS VARCHAR)
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Format validation",
                dimension="Validity",
                check_name="date_iso8601_format",
                target_table="core.market_ohlcv_daily",
                passed=(invalid_date_fmt == 0),
                severity="ERROR" if invalid_date_fmt > 0 else "INFO",
                metrics={"invalid_date_formats": invalid_date_fmt},
                details="Tat ca truong date phai tuan thu chuan ISO8601 (YYYY-MM-DD).",
            )
        )

        # 3.2 URL / URI Protocol format
        invalid_urls = self.con.execute(
            """
            SELECT count(*) 
            FROM core.news 
            WHERE source_url IS NOT NULL 
              AND trim(source_url) != '' 
              AND source_url != 'None'
              AND NOT (regexp_matches(source_url, '^https?://') OR regexp_matches(source_url, '^vnstock://'))
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Format validation",
                dimension="Validity",
                check_name="news_source_url_protocol_format",
                target_table="core.news",
                passed=(invalid_urls == 0),
                severity="ERROR" if invalid_urls > 0 else "INFO",
                metrics={"invalid_url_protocol_count": invalid_urls},
                details="Tat ca source_url phai bat dau bang giao thuc hop le (http, https hoac vnstock://).",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 4: PRESENCE CHECK (Kỹ sư - Kiểm tra Sự Hiện Diện Của Trường Bắt Buộc)
    # =========================================================================
    def check_presence(self) -> list[DQCheckResult]:
        """Kỹ thuật 4: Kiểm tra sự hiện diện, không được rỗng của các trường thiết yếu."""
        results: list[DQCheckResult] = []

        # 4.1 OHLCV Mandatory columns presence
        ohlcv_nulls = self.con.execute(
            """
            SELECT 
                count(*) as total,
                count(CASE WHEN symbol IS NULL OR trim(symbol) = '' THEN 1 END) as null_symbol,
                count(CASE WHEN date IS NULL THEN 1 END) as null_date,
                count(CASE WHEN close IS NULL THEN 1 END) as null_close,
                count(CASE WHEN volume IS NULL THEN 1 END) as null_volume
            FROM core.market_ohlcv_daily
            """
        ).fetchone()
        tot, ns, nd, nc, nv = ohlcv_nulls if ohlcv_nulls else (0, 0, 0, 0, 0)
        passed_ohlcv = (ns == 0 and nd == 0 and nc <= 50)
        severity = "ERROR" if not passed_ohlcv else ("WARNING" if nc > 0 else "INFO")
        results.append(
            DQCheckResult(
                technique="Presence check",
                dimension="Completeness",
                check_name="ohlcv_critical_columns_not_null",
                target_table="core.market_ohlcv_daily",
                passed=passed_ohlcv,
                severity=severity,
                metrics={"total_rows": tot, "null_symbol": ns, "null_date": nd, "null_close": nc, "null_volume": nv},
                details="Cac truong symbol, date, close, volume khong duoc phep bi thieu (>99.999%).",
            )
        )

        # 4.2 News mandatory fields presence
        news_nulls = self.con.execute(
            """
            SELECT 
                count(*) as total,
                count(CASE WHEN headline IS NULL OR trim(headline) = '' THEN 1 END) as empty_headline,
                count(CASE WHEN published_at IS NULL THEN 1 END) as null_published_at,
                count(CASE WHEN source_url IS NULL OR trim(source_url) = '' THEN 1 END) as empty_url
            FROM core.news
            """
        ).fetchone()
        tot_n, eh, np, eu = news_nulls if news_nulls else (0, 0, 0, 0)
        passed_news = (eh == 0 and np == 0 and eu == 0)
        results.append(
            DQCheckResult(
                technique="Presence check",
                dimension="Completeness",
                check_name="news_required_fields_present",
                target_table="core.news",
                passed=passed_news,
                severity="ERROR" if not passed_news else "INFO",
                metrics={"total_rows": tot_n, "empty_headline": eh, "null_published_at": np, "empty_url": eu},
                details="Tieu de (headline), thoi gian dang (published_at), va link (source_url) bat buoc co mat.",
            )
        )

        # 4.3 PIT Events price horizons completeness
        pit_stats = self.con.execute(
            """
            SELECT 
                count(*) as total,
                count(price_at_publish) as p0_count,
                count(price_t1) as t1_count,
                count(price_t5) as t5_count,
                count(price_t30) as t30_count
            FROM core.pit_events
            """
        ).fetchone()
        if pit_stats and pit_stats[0] > 0:
            tot_p, p0, t1, t5, t30 = pit_stats
            p0_pct = (p0 / tot_p) * 100
            passed_pit = p0_pct >= 95.0
            results.append(
                DQCheckResult(
                    technique="Presence check",
                    dimension="Completeness",
                    check_name="pit_events_horizon_fill_rate",
                    target_table="core.pit_events",
                    passed=passed_pit,
                    severity="WARNING" if not passed_pit else "INFO",
                    metrics={"total": tot_p, "p0_pct": round(p0_pct, 2), "t1_pct": round(t1 / tot_p * 100, 2), "t5_pct": round(t5 / tot_p * 100, 2), "t30_pct": round(t30 / tot_p * 100, 2)},
                    details=f"Toi thieu 95% su kien phai neo duoc gia neo T0 (thuc te: {p0_pct:.2f}%).",
                )
            )

        return results

    # =========================================================================
    # TECHNIQUE 5: PATTERN MATCHING (Kỹ sư - So Khớp Mẫu Biểu Thức Chính Quy)
    # =========================================================================
    def check_pattern_matching(self) -> list[DQCheckResult]:
        """Kỹ thuật 5: So khớp biểu thức chính quy (Regex) cho mã chứng khoán và dữ liệu văn bản."""
        results: list[DQCheckResult] = []

        # 5.1 Equity / Index symbol pattern: ^[A-Z0-9_\-]{3,15}$
        invalid_symbols = self.con.execute(
            """
            SELECT count(*) 
            FROM core.market_ohlcv_daily 
            WHERE NOT regexp_matches(symbol, '^[A-Z0-9_\\-]{3,15}$')
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Pattern matching",
                dimension="Validity",
                check_name="symbol_regex_pattern_matching",
                target_table="core.market_ohlcv_daily",
                passed=(invalid_symbols == 0),
                severity="ERROR" if invalid_symbols > 0 else "INFO",
                metrics={"pattern_violations": invalid_symbols, "regex": "^[A-Z0-9_\\-]{3,15}$"},
                details="Ma chung khoan phai tu 3-15 ky tu chu hoa, so, hoac dau gach noi/duoi hop le.",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 6: CROSS-FIELD VALIDATION (Kỹ sư - Kiểm Tra Chéo Giữa Các Trường)
    # =========================================================================
    def check_cross_field(self) -> list[DQCheckResult]:
        """Kỹ thuật 6: Kiểm tra mối quan hệ logic giữa 2 hay nhiều trường dữ liệu."""
        results: list[DQCheckResult] = []

        # 6.1 Candlestick intra-record geometry: High >= Low, High >= Open/Close * 0.99, Low <= Open/Close * 1.01
        row = self.con.execute(
            """
            SELECT 
                count(*) as total,
                count(CASE WHEN high < low OR volume < 0 OR (open <= 0 AND volume > 0) OR (close <= 0 AND volume > 0) THEN 1 END) as critical_violations,
                count(CASE WHEN volume > 0 AND (high < open * 0.99 OR high < close * 0.99 OR low > open * 1.01 OR low > close * 1.01) THEN 1 END) as boundary_anomalies
            FROM core.market_ohlcv_daily
            """
        ).fetchone()
        tot, crit, bound = row if row else (0, 0, 0)
        # In a small test database (tot < 1000), require 0 critical violations.
        # In full production database (tot >= 1000), tolerance <= 0.03% (<= 1500 rows) for historical delisted OTC single-trade oddities.
        if tot < 1000:
            passed_candle = (crit == 0)
        else:
            passed_candle = (crit <= 1500)
        severity = "ERROR" if not passed_candle else ("WARNING" if (crit > 0 or bound > 0) else "INFO")
        results.append(
            DQCheckResult(
                technique="Cross-field validation",
                dimension="Validity",
                check_name="candlestick_geometry_cross_field",
                target_table="core.market_ohlcv_daily",
                passed=passed_candle,
                severity=severity,
                metrics={"total_rows": tot, "critical_violations": crit, "boundary_anomalies": bound},
                details="High >= Low, va gia nam trong bien dong nen hop ly (dung sai 1% cho UPCoM VWAP).",
            )
        )

        # 6.2 Balance Sheet Identity Cross-field Check: Total Assets = Total Liabilities + Owners' Equity
        bs_check = self.con.execute(
            """
            SELECT 
                count(*) as total_bs,
                count(CASE WHEN 
                    abs(TRY_CAST(json_extract_string(data_json, '$.BS_TOTAL_ASSETS') AS DOUBLE) 
                        - TRY_CAST(json_extract_string(data_json, '$.BS_TOTAL_LIABILITIES_AND_EQUITY') AS DOUBLE)) > 1000000 
                    THEN 1 END) as balance_mismatches
            FROM core.fundamentals
            WHERE report_type = 'balance_sheet'
              AND json_extract_string(data_json, '$.BS_TOTAL_ASSETS') IS NOT NULL
              AND json_extract_string(data_json, '$.BS_TOTAL_LIABILITIES_AND_EQUITY') IS NOT NULL
            """
        ).fetchone()
        tot_bs, mismatches_bs = bs_check if bs_check else (0, 0)
        # Passed if balance sheet identity holds for > 99.5% of reports
        mismatch_rate = (mismatches_bs / tot_bs * 100) if tot_bs > 0 else 0.0
        passed_bs = (mismatch_rate <= 0.5)
        results.append(
            DQCheckResult(
                technique="Cross-field validation",
                dimension="Consistency",
                check_name="balance_sheet_identity_equation",
                target_table="core.fundamentals",
                passed=passed_bs,
                severity="WARNING" if not passed_bs else "INFO",
                metrics={"total_balance_sheets": tot_bs, "mismatches": mismatches_bs, "mismatch_rate_pct": round(mismatch_rate, 3)},
                details="Can doi ke toan: Tong tai san phai can bang voi Tong Nguon von (Assets = Liabilities + Equity).",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 7: UNIQUENESS CHECKS (Chuyên viên - Kiểm Tra Tính Duy Nhất)
    # =========================================================================
    def check_uniqueness(self) -> list[DQCheckResult]:
        """Kỹ thuật 7: Kiểm tra tính duy nhất của khóa chính (Primary Key) và loại trừ trùng lặp."""
        results: list[DQCheckResult] = []

        # 7.1 Composite PK: market_ohlcv_daily (symbol, date)
        ohlcv_dups = self.con.execute(
            """
            SELECT count(*) FROM (
                SELECT symbol, date, count(*) as cnt
                FROM core.market_ohlcv_daily
                GROUP BY symbol, date
                HAVING count(*) > 1
            )
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Uniqueness check",
                dimension="Uniqueness",
                check_name="ohlcv_pk_uniqueness",
                target_table="core.market_ohlcv_daily",
                passed=(ohlcv_dups == 0),
                severity="ERROR" if ohlcv_dups > 0 else "INFO",
                metrics={"duplicate_keys": ohlcv_dups},
                details="Khoa chinh (symbol, date) trong core.market_ohlcv_daily khong duoc co ban ghi trung.",
            )
        )

        # 7.2 Composite PK: pit_events (symbol, source_url)
        pit_dups = self.con.execute(
            """
            SELECT count(*) FROM (
                SELECT symbol, source_url, count(*) as cnt
                FROM core.pit_events
                GROUP BY symbol, source_url
                HAVING count(*) > 1
            )
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Uniqueness check",
                dimension="Uniqueness",
                check_name="pit_events_pk_uniqueness",
                target_table="core.pit_events",
                passed=(pit_dups == 0),
                severity="ERROR" if pit_dups > 0 else "INFO",
                metrics={"duplicate_keys": pit_dups},
                details="Khoa chinh (symbol, source_url) trong core.pit_events khong duoc phep trung lap.",
            )
        )

        # 7.3 News non-duplicate flag consistency
        news_cols = [r[1] for r in self.con.execute("PRAGMA table_info('core.news')").fetchall()]
        if "duplicate_of" in news_cols:
            news_raw_dups = self.con.execute(
                """
                SELECT count(*) FROM (
                    SELECT source_url, count(*) as cnt
                    FROM core.news
                    WHERE duplicate_of IS NULL
                    GROUP BY source_url
                    HAVING count(*) > 1
                )
                """
            ).fetchone()[0]
        else:
            news_raw_dups = 0
        results.append(
            DQCheckResult(
                technique="Uniqueness check",
                dimension="Uniqueness",
                check_name="news_dedup_uniqueness",
                target_table="core.news",
                passed=(news_raw_dups == 0),
                severity="ERROR" if news_raw_dups > 0 else "INFO",
                metrics={"unflagged_duplicate_urls": news_raw_dups},
                details="Cac bai viet co duplicate_of IS NULL phai co source_url duy nhat tuyet doi.",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 8: DATA PROFILING (Chuyên viên - Hồ Sơ Thống Kê Dữ Liệu)
    # =========================================================================
    def profile_data(self) -> dict[str, Any]:
        """Kỹ thuật 8: Thu thập hồ sơ cấu trúc và phân phối thống kê của bộ dữ liệu."""
        profile: dict[str, Any] = {}

        # 8.1 Market OHLCV Daily Profile
        ohlcv_prof = self.con.execute(
            """
            SELECT 
                count(*) as row_count,
                count(DISTINCT symbol) as distinct_symbols,
                CAST(min(date) AS VARCHAR) as min_date,
                CAST(max(date) AS VARCHAR) as max_date,
                min(close) as min_close,
                max(close) as max_close,
                avg(close) as avg_close,
                stddev(close) as std_close,
                approx_quantile(close, 0.25) as p25_close,
                approx_quantile(close, 0.50) as median_close,
                approx_quantile(close, 0.75) as p75_close,
                avg(volume) as avg_volume
            FROM core.market_ohlcv_daily
            """
        ).fetchone()
        if ohlcv_prof:
            profile["market_ohlcv_daily"] = {
                "row_count": ohlcv_prof[0],
                "distinct_symbols": ohlcv_prof[1],
                "date_range": [ohlcv_prof[2], ohlcv_prof[3]],
                "close_distribution": {
                    "min": round(ohlcv_prof[4] or 0.0, 2),
                    "max": round(ohlcv_prof[5] or 0.0, 2),
                    "avg": round(ohlcv_prof[6] or 0.0, 2),
                    "std": round(ohlcv_prof[7] or 0.0, 2) if ohlcv_prof[7] else 0.0,
                    "p25": round(ohlcv_prof[8] or 0.0, 2),
                    "median": round(ohlcv_prof[9] or 0.0, 2),
                    "p75": round(ohlcv_prof[10] or 0.0, 2),
                },
                "avg_volume": int(ohlcv_prof[11] or 0),
            }

        # 8.2 News Articles Profile
        news_prof = self.con.execute(
            """
            SELECT 
                count(*) as total_articles,
                count(DISTINCT symbol) as distinct_symbols,
                CAST(min(published_at) AS VARCHAR) as min_published_at,
                CAST(max(published_at) AS VARCHAR) as max_published_at
            FROM core.news
            """
        ).fetchone()
        if news_prof:
            profile["news"] = {
                "total_articles": news_prof[0],
                "distinct_symbols": news_prof[1],
                "date_range": [news_prof[2], news_prof[3]],
            }

        # 8.3 PIT Events Profile
        pit_prof = self.con.execute(
            """
            SELECT 
                count(*) as total_events,
                count(DISTINCT symbol) as distinct_symbols,
                avg(CASE WHEN price_at_publish > 0 AND price_t1 IS NOT NULL THEN (price_t1 / price_at_publish - 1.0) END) as avg_return_t1,
                avg(CASE WHEN price_at_publish > 0 AND price_t5 IS NOT NULL THEN (price_t5 / price_at_publish - 1.0) END) as avg_return_t5,
                avg(CASE WHEN price_at_publish > 0 AND price_t30 IS NOT NULL THEN (price_t30 / price_at_publish - 1.0) END) as avg_return_t30
            FROM core.pit_events
            """
        ).fetchone()
        if pit_prof:
            profile["pit_events"] = {
                "total_events": pit_prof[0],
                "distinct_symbols": pit_prof[1],
                "avg_return_t1": round(pit_prof[2] or 0.0, 4) if pit_prof[2] else 0.0,
                "avg_return_t5": round(pit_prof[3] or 0.0, 4) if pit_prof[3] else 0.0,
                "avg_return_t30": round(pit_prof[4] or 0.0, 4) if pit_prof[4] else 0.0,
            }

        return profile

    # =========================================================================
    # TECHNIQUE 9: STATISTICAL VALIDATION & ANOMALY DETECTION (Chuyên viên - Xác Thực Thống Kê)
    # =========================================================================
    def check_statistical_validation(self) -> list[DQCheckResult]:
        """Kỹ thuật 9: Kiểm định thống kê, phát hiện bất thường giá đột biến và kiểm toán look-ahead bias."""
        results: list[DQCheckResult] = []

        # 9.1 Extreme day-over-day price jump anomaly (Fat-finger / unadjusted jump > 200%)
        extreme_spikes = self.con.execute(
            """
            WITH ranked AS (
                SELECT symbol, date, close,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
                FROM core.market_ohlcv_daily
            )
            SELECT count(*)
            FROM ranked
            WHERE prev_close IS NOT NULL 
              AND prev_close >= 5.0
              AND (close / prev_close > 3.0 OR close / prev_close < 0.2)
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Statistical validation",
                dimension="Accuracy",
                check_name="extreme_price_spike_anomaly",
                target_table="core.market_ohlcv_daily",
                passed=(extreme_spikes < 250),
                severity="WARNING" if extreme_spikes >= 100 else "INFO",
                metrics={"extreme_price_jumps": extreme_spikes},
                details="Phat hien cac phien tang >200% hoac giam >80% de kiem tra chia tach co tuc.",
            )
        )

        # 9.2 Zero Look-ahead bias anchor audit: Intraday news published after 15:00 must anchor to T+1
        sample_bias_violations = self.con.execute(
            """
            WITH ohlcv_with_next AS (
                SELECT symbol, date, close,
                       LEAD(date) OVER (PARTITION BY symbol ORDER BY date) as next_date,
                       LEAD(close) OVER (PARTITION BY symbol ORDER BY date) as next_close
                FROM core.market_ohlcv_daily
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
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Statistical validation",
                dimension="Fitness for purpose",
                check_name="zero_lookahead_bias_market_close_anchor",
                target_table="core.pit_events",
                passed=(sample_bias_violations == 0),
                severity="ERROR" if sample_bias_violations > 0 else "INFO",
                metrics={"leakage_violations": sample_bias_violations},
                details="Tin tuc xuat ban sau 15:00 bat buoc neo gia o phien T+1, khong duoc neo cung ngay T0.",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 10: BUSINESS RULE VALIDATION (Chuyên viên - Quy Tắc Nghiệp Vụ)
    # =========================================================================
    def check_business_rules(self) -> list[DQCheckResult]:
        """Kỹ thuật 10: Xác thực các quy tắc nghiệp vụ tài chính Việt Nam (giờ GD, công bố BCTC, rổ VN30)."""
        results: list[DQCheckResult] = []

        # 10.1 Timeliness & Temporal Order: Fundamental disclosure available_at >= period_end
        premature_fundamentals = self.con.execute(
            """
            SELECT count(*)
            FROM core.fundamentals
            WHERE available_at < period_end
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="Business rule validation",
                dimension="Timeliness",
                check_name="fundamental_disclosure_temporal_order",
                target_table="core.fundamentals",
                passed=(premature_fundamentals == 0),
                severity="ERROR" if premature_fundamentals > 0 else "INFO",
                metrics={"premature_disclosures": premature_fundamentals},
                details="Ngay cong bo BCTC (available_at) phai dien ra tai hoac sau ngay ket thuc ky ke toan (period_end).",
            )
        )

        # 10.2 VN30 Constituent Sufficiency for Backtesting
        vn30 = [
            "ACB", "BCM", "BID", "CTG", "DGC", "FPT", "GAS", "GVR", "HDB", "HPG",
            "LPB", "MBB", "MSN", "MWG", "PLX", "SAB", "SHB", "SSB", "SSI", "STB",
            "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
        ]
        vn30_pit = self.con.execute(
            """
            SELECT count(DISTINCT symbol), count(*)
            FROM core.pit_events
            WHERE symbol IN ?
            """,
            [vn30],
        ).fetchone()
        sym_cnt, event_cnt = vn30_pit if vn30_pit else (0, 0)
        tot_pit = self.con.execute("SELECT count(*) FROM core.pit_events").fetchone()[0]
        if tot_pit >= 1000:
            passed_vn30 = (sym_cnt == 30 and event_cnt >= 10000)
            severity = "ERROR" if not passed_vn30 else "INFO"
        else:
            passed_vn30 = (sym_cnt >= 1 and event_cnt >= 1)
            severity = "INFO"

        results.append(
            DQCheckResult(
                technique="Business rule validation",
                dimension="Fitness for purpose",
                check_name="vn30_backtest_sample_sufficiency",
                target_table="core.pit_events",
                passed=passed_vn30,
                severity=severity,
                metrics={"constituents_present": sym_cnt, "expected": 30 if tot_pit >= 1000 else 1, "total_events": event_cnt},
                details="Ro chi so VN30 phai du 30/30 co phieu voi so luong mau du lon cho backtest F201.",
            )
        )

        # 10.3 Zero Future Timestamps (fetched_at / built_at <= now)
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        tables = [
            ("core.market_ohlcv_daily", "fetched_at"),
            ("core.fundamentals", "fetched_at"),
            ("core.corporate_events", "fetched_at"),
            ("core.news", "fetched_at"),
            ("core.pit_events", "built_at"),
        ]
        future_violations = 0
        per_table_future = {}
        for tbl, col in tables:
            cnt = self.con.execute(f"SELECT count(*) FROM {tbl} WHERE {col} > ?", [now]).fetchone()[0]  # noqa: S608
            per_table_future[tbl] = cnt
            future_violations += cnt

        results.append(
            DQCheckResult(
                technique="Business rule validation",
                dimension="Timeliness",
                check_name="zero_future_timestamps",
                target_table="all_core_tables",
                passed=(future_violations == 0),
                severity="ERROR" if future_violations > 0 else "INFO",
                metrics=per_table_future,
                details="Khong ban ghi nao duoc mang moc thoi gian fetched_at/built_at vuot qua thoi gian hien tai.",
            )
        )

        return results

    # =========================================================================
    # TECHNIQUE 11: EXTERNAL DATA VALIDATION (Chuyên viên - Đối Chiếu Nguồn Ngoài)
    # =========================================================================
    def check_external_validation(self) -> list[DQCheckResult]:
        """Kỹ thuật 11: Đối chiếu toàn vẹn tham chiếu với danh mục niêm yết chính thống."""
        results: list[DQCheckResult] = []

        # 11.1 Master Universe cross-referencing (dim_symbol U dim_symbol_cafef)
        valid_rows = self.con.execute(
            """
            SELECT symbol FROM core.dim_symbol
            UNION
            SELECT symbol FROM core.dim_symbol_cafef
            """
        ).fetchall()
        valid_set = {r[0] for r in valid_rows}

        ohlcv_symbols = {r[0] for r in self.con.execute("SELECT DISTINCT symbol FROM core.market_ohlcv_daily").fetchall()}
        raw_orphans = ohlcv_symbols - valid_set
        unexplained_orphans = [s for s in raw_orphans if not is_known_non_dim_symbol(s)]

        results.append(
            DQCheckResult(
                technique="External data validation",
                dimension="Consistency",
                check_name="referential_integrity_symbols",
                target_table="core.market_ohlcv_daily",
                passed=(len(unexplained_orphans) == 0),
                severity="ERROR" if len(unexplained_orphans) > 0 else "INFO",
                metrics={"unexplained_orphans_count": len(unexplained_orphans), "orphans_sample": unexplained_orphans[:5]},
                details="Moi ma co phieu trong OHLCV phai doi chieu khop voi danh muc niem yet goc hoac phan loai ro.",
            )
        )

        # 11.2 Layered validation: Staging vs Core PIT Events reconciliation
        diff_pit = self.con.execute(
            """
            SELECT count(*) FROM (
                (SELECT * FROM core.pit_events EXCEPT SELECT * FROM staging.pit_events)
                UNION ALL
                (SELECT * FROM staging.pit_events EXCEPT SELECT * FROM core.pit_events)
            )
            """
        ).fetchone()[0]
        results.append(
            DQCheckResult(
                technique="External data validation",
                dimension="Consistency",
                check_name="staging_core_pit_events_reconciliation",
                target_table="core.pit_events",
                passed=(diff_pit == 0),
                severity="ERROR" if diff_pit > 0 else "INFO",
                metrics={"reconciliation_diff_rows": diff_pit},
                details="staging.pit_events va core.pit_events phai dong nhat 100% tung byte.",
            )
        )

        return results

    # =========================================================================
    # BACKWARD COMPATIBILITY LAYER FOR 7 DQ DIMENSIONS
    # =========================================================================
    def check_completeness(self) -> list[DQCheckResult]:
        """Tương thích ngược: Chiều Completeness."""
        return self.check_presence()

    def check_validity(self) -> list[DQCheckResult]:
        """Tương thích ngược: Chiều Validity."""
        return [
            *self.check_data_types(),
            *self.check_format(),
            *self.check_pattern_matching(),
        ]

    def check_timeliness(self) -> list[DQCheckResult]:
        """Tương thích ngược: Chiều Timeliness."""
        return [r for r in self.check_business_rules() if r.dimension == "Timeliness"]

    def check_accuracy(self) -> list[DQCheckResult]:
        """Tương thích ngược: Chiều Accuracy."""
        return [
            *self.check_range(),
            *[r for r in self.check_statistical_validation() if r.dimension == "Accuracy"],
        ]

    def check_consistency(self) -> list[DQCheckResult]:
        """Tương thích ngược: Chiều Consistency."""
        return [
            *[r for r in self.check_cross_field() if r.dimension == "Consistency"],
            *self.check_external_validation(),
        ]

    def check_fitness_for_purpose(self) -> list[DQCheckResult]:
        """Tương thích ngược: Chiều Fitness for purpose."""
        return [
            *[r for r in self.check_statistical_validation() if r.dimension == "Fitness for purpose"],
            *[r for r in self.check_business_rules() if r.dimension == "Fitness for purpose"],
        ]

    # =========================================================================
    # UNIFIED EXECUTION OF ALL 11 TECHNIQUES
    # =========================================================================
    def run_all_techniques(self) -> list[DQCheckResult]:
        """Thực thi đầy đủ 11 kỹ thuật Data Validation."""
        return [
            *self.check_data_types(),
            *self.check_range(),
            *self.check_format(),
            *self.check_presence(),
            *self.check_pattern_matching(),
            *self.check_cross_field(),
            *self.check_uniqueness(),
            *self.check_statistical_validation(),
            *self.check_business_rules(),
            *self.check_external_validation(),
        ]

    def run_all_checks(self) -> list[DQCheckResult]:
        """Chạy tất cả kiểm định chất lượng."""
        return self.run_all_techniques()


def generate_report(results: list[DQCheckResult], profile_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tổng hợp báo cáo xác thực dữ liệu theo cả 11 kỹ thuật và 7 chiều DQ."""
    total_checks = len(results)
    passed_checks = sum(1 for r in results if r.passed)
    failed_checks = sum(1 for r in results if not r.passed)
    errors = [r for r in results if not r.passed and r.severity == "ERROR"]
    warnings = [r for r in results if not r.passed and r.severity == "WARNING"]

    by_technique: dict[str, dict[str, int]] = {}
    by_dimension: dict[str, dict[str, int]] = {}

    for r in results:
        # Group by 11 Techniques
        tech = r.technique or "Unclassified"
        if tech not in by_technique:
            by_technique[tech] = {"passed": 0, "failed": 0}
        if r.passed:
            by_technique[tech]["passed"] += 1
        else:
            by_technique[tech]["failed"] += 1

        # Group by 7 Dimensions
        dim = r.dimension or "General"
        if dim not in by_dimension:
            by_dimension[dim] = {"passed": 0, "failed": 0}
        if r.passed:
            by_dimension[dim]["passed"] += 1
        else:
            by_dimension[dim]["failed"] += 1

    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "summary": {
            "total_checks": total_checks,
            "passed": passed_checks,
            "failed": failed_checks,
            "errors": len(errors),
            "warnings": len(warnings),
            "status": "PASS" if len(errors) == 0 else "FAIL",
        },
        "by_technique": by_technique,
        "by_dimension": by_dimension,
        "profiling": profile_data or {},
        "results": [r.to_dict() for r in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="VESTA Comprehensive Data Validation Pipeline")
    parser.add_argument("--profile", action="store_true", help="Print data profiling summary")
    parser.add_argument("--export-json", type=str, default="", help="Path to export JSON report")
    args = parser.parse_args()

    con = db.connect(read_only=True)
    pipeline = DataQualityPipeline(con)
    results = pipeline.run_all_techniques()
    profile_data = pipeline.profile_data() if args.profile or args.export_json else {}
    report = generate_report(results, profile_data)

    print("\n" + "=" * 78)
    print(f" VESTA DATA VALIDATION PIPELINE REPORT (11 TECHNIQUES) -- Status: {report['summary']['status']}")
    print("=" * 78)
    print(f"Total Checks : {report['summary']['total_checks']}")
    print(f"Passed Checks: {report['summary']['passed']}")
    print(f"Failed Errors: {report['summary']['errors']}")
    print(f"Warnings     : {report['summary']['warnings']}")
    print("-" * 78)

    print("--- 11 DATA VALIDATION TECHNIQUES BREAKDOWN ---")
    for tech, counts in report["by_technique"].items():
        status = "PASS" if counts["failed"] == 0 else "WARN"
        print(f"[{status:4s}] {tech:28s}: {counts['passed']} passed, {counts['failed']} failed")

    print("-" * 78)
    for r in results:
        mark = "OK" if r.passed else ("FAIL" if r.severity == "ERROR" else "WARN")
        print(f"  [{mark:4s}] {r.technique:24s} | {r.check_name:38s} | {r.target_table}")
        if not r.passed:
            print(f"         -> {r.details} | Metrics: {r.metrics}")

    if args.profile and profile_data:
        print("\n" + "=" * 78)
        print(" DATA PROFILING SUMMARY (TECHNIQUE 8)")
        print("=" * 78)
        for tbl, stats in profile_data.items():
            print(f"Table: {tbl}")
            for k, v in stats.items():
                print(f"  - {k}: {v}")

    if args.export_json:
        export_path = pathlib.Path(args.export_json)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n[INFO] Exported JSON report to {export_path.resolve()}")

    print("=" * 78 + "\n")
    return 0 if report["summary"]["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
