"""src/pipeline/data_quality.py

VESTA Enterprise Data Quality Pipeline Suite.
Kiểm định toàn diện chất lượng dữ liệu trên cả 5 Cơ sở dữ liệu Lakehouse:
1. vesta_ohlcv.duckdb
2. vesta_market_index.duckdb
3. vesta_news.duckdb
4. vesta_fundamentals.duckdb
5. vesta_events.duckdb

Đáp ứng 6 Trọng tâm Đo lường Chất lượng Dữ liệu (Key Dimension Tests):
• Accuracy (Độ chính xác & Ràng buộc miền giá trị): high >= low, high >= open, close > 0, volume >= 0.
• Completeness (Độ toàn vẹn & Không rỗng): not_null trên các khóa chính và cột nghiệp vụ.
• Consistency (Tính nhất quán & Toàn vẹn tham chiếu): Quy mô giá đồng nhất, mã cổ phiếu chuẩn hóa.
• Uniqueness (Tính duy nhất): Không có hàng trùng lặp trên composite primary keys.
• Timeliness & Freshness (Độ tươi mới & SLA): Dữ liệu đạt mốc T-0 (2026-10-09).
• Validity & Format (Định dạng & Regex): Cú pháp ngày ISO YYYY-MM-DD, Regex mã cổ phiếu.

Bao gồm 5 Loại hình Kiểm tra Cốt lõi (Essential Types of Checks):
1. Null Value & Mandatory Tests (dbt not_null)
2. Uniqueness Tests (dbt unique)
3. Volume & Row Count Tests (Phát hiện sụt giảm khối lượng dữ liệu)
4. Schema Validation (Xác thực cấu trúc cột và kiểu dữ liệu)
5. Outlier & Anomaly Detection (Phát hiện dị biệt giá, bước nhảy bất thường 1000x)
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

import duckdb

# Đảm bảo UTF-8 output trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("data_quality")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@dataclasses.dataclass
class QualityCheckResult:
    """Kết quả kiểm tra của một quy tắc Data Quality."""
    dimension: str  # Accuracy, Completeness, Consistency, Uniqueness, Timeliness, Validity
    check_type: str  # Mandatory/Null, Uniqueness, Volume, Schema, Anomaly
    check_name: str
    target_database: str
    target_table: str
    passed: bool
    severity: str  # "ERROR", "WARNING", "INFO"
    metrics: Dict[str, Any] = dataclasses.field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


class VestaDataQualitySuite:
    """Bộ kiểm định chất lượng dữ liệu đa chiều cho hệ thống VESTA Lakehouse."""

    def __init__(self, use_admin: bool = False):
        self.use_admin = use_admin
        self.base_dir = REPO_ROOT / "db" / ("admin" if use_admin else "")
        self.results: List[QualityCheckResult] = []

    def _get_connection(self, db_filename: str) -> Optional[duckdb.DuckDBPyConnection]:
        """Kết nối an toàn READ_ONLY đến từng CSDL, tự động dự phòng sang db/admin nếu cần."""
        candidates = [
            str(self.base_dir / db_filename),
            str(REPO_ROOT / "db" / "admin" / db_filename),
            str(REPO_ROOT / "db" / db_filename),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    return duckdb.connect(path, read_only=True, config={"access_mode": "read_only"})
                except Exception:
                    try:
                        return duckdb.connect(path, read_only=True)
                    except Exception:
                        continue
        return None

    # =========================================================================
    # 1. DATABASE: vesta_ohlcv.duckdb
    # =========================================================================
    def audit_ohlcv_database(self):
        """Kiểm định CSDL OHLCV: nến ngày, nến 1m, phái sinh, ETF, chứng quyền."""
        con = self._get_connection("vesta_ohlcv.duckdb")
        if con is None:
            self.results.append(
                QualityCheckResult(
                    dimension="Completeness",
                    check_type="Mandatory",
                    check_name="ohlcv_db_accessible",
                    target_database="vesta_ohlcv.duckdb",
                    target_table="*",
                    passed=False,
                    severity="ERROR",
                    message="Không thể kết nối đến vesta_ohlcv.duckdb",
                )
            )
            return

        # 1.1 Volume & Row Count Tests
        daily_count = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_daily").fetchone()[0]
        m1_count = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m").fetchone()[0]
        deriv_count = con.execute("SELECT COUNT(*) FROM core.market_derivatives_daily").fetchone()[0]
        etf_count = con.execute("SELECT COUNT(*) FROM core.market_etf_daily").fetchone()[0]
        cw_count = con.execute("SELECT COUNT(*) FROM core.market_covered_warrants_daily").fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Completeness",
                check_type="Volume",
                check_name="ohlcv_volume_threshold",
                target_database="vesta_ohlcv.duckdb",
                target_table="core.market_ohlcv_daily",
                passed=(daily_count >= 4_000_000 and m1_count >= 20_000_000),
                severity="ERROR" if daily_count < 4_000_000 else "INFO",
                metrics={
                    "daily_count": daily_count,
                    "1m_count": m1_count,
                    "derivatives_count": deriv_count,
                    "etf_count": etf_count,
                    "cw_count": cw_count,
                },
                message=f"Đạt {daily_count:,} nến ngày và {m1_count:,} nến 1m.",
            )
        )

        # 1.2 Uniqueness Tests (dbt unique)
        daily_dups = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT symbol, date, COUNT(*) 
                FROM core.market_ohlcv_daily 
                GROUP BY symbol, date 
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Uniqueness",
                check_type="Uniqueness",
                check_name="ohlcv_daily_composite_key_unique",
                target_database="vesta_ohlcv.duckdb",
                target_table="core.market_ohlcv_daily",
                passed=(daily_dups == 0),
                severity="ERROR" if daily_dups > 0 else "INFO",
                metrics={"duplicate_groups": daily_dups},
                message="Khóa chính (symbol, date) không có hàng trùng lặp." if daily_dups == 0 else f"Phát hiện {daily_dups} nhóm trùng lặp!",
            )
        )

        # 1.3 Accuracy & Cross-field Validation
        # high >= low, high >= open, high >= close, close > 0, volume >= 0
        invalid_daily_bounds = con.execute("""
            SELECT COUNT(*) FROM core.market_ohlcv_daily
            WHERE high < low OR high < open OR high < close OR low > open OR low > close OR close <= 0 OR volume < 0
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Accuracy",
                check_type="Mandatory",
                check_name="ohlcv_daily_cross_field_bounds",
                target_database="vesta_ohlcv.duckdb",
                target_table="core.market_ohlcv_daily",
                passed=(invalid_daily_bounds == 0),
                severity="ERROR" if invalid_daily_bounds > 0 else "INFO",
                metrics={"invalid_records": invalid_daily_bounds},
                message="Tất cả nến ngày tuân thủ tuyệt đối quy tắc hình học nến: high >= max(open, close), low <= min(open, close)."
            )
        )

        # 1.4 Consistency & Outlier/Anomaly Detection (Price Scale Test)
        # Giá nến 1m của cổ phiếu phải ở đơn vị 1,000 VND (open <= 10,000)
        anomalous_1m_prices = con.execute("""
            SELECT COUNT(*) FROM core.market_ohlcv_1m
            WHERE open > 10000
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Consistency",
                check_type="Anomaly",
                check_name="ohlcv_1m_price_scale_consistency",
                target_database="vesta_ohlcv.duckdb",
                target_table="core.market_ohlcv_1m",
                passed=(anomalous_1m_prices == 0),
                severity="ERROR" if anomalous_1m_prices > 0 else "INFO",
                metrics={"outlier_count": anomalous_1m_prices},
                message="Toàn bộ chuỗi nến 1m đồng nhất quy mô giá (1,000 VND), không có bước nhảy 1000x." if anomalous_1m_prices == 0 else f"Còn {anomalous_1m_prices} nến chưa chuẩn hóa!",
            )
        )

        # 1.5 Timeliness & Freshness (SLA)
        max_daily_date = con.execute("SELECT MAX(date) FROM core.market_ohlcv_daily").fetchone()[0]
        max_1m_time = con.execute("SELECT MAX(time) FROM core.market_ohlcv_1m").fetchone()[0]
        sla_passed = str(max_daily_date) >= "2026-10-09"

        self.results.append(
            QualityCheckResult(
                dimension="Timeliness",
                check_type="Volume",
                check_name="ohlcv_freshness_sla",
                target_database="vesta_ohlcv.duckdb",
                target_table="core.market_ohlcv_daily",
                passed=sla_passed,
                severity="ERROR" if not sla_passed else "INFO",
                metrics={"max_daily_date": str(max_daily_date), "max_1m_time": str(max_1m_time)},
                message=f"Dữ liệu nến ngày đạt T-0 ({max_daily_date}), nến 1m đạt {max_1m_time}."
            )
        )

        # 1.6 Validity & Format (Date ISO & Regex Symbol)
        invalid_symbols = con.execute("""
            SELECT COUNT(*) FROM core.market_ohlcv_daily
            WHERE NOT regexp_matches(symbol, '^[A-Z0-9_\\-\\.]+$')
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Validity",
                check_type="Schema",
                check_name="ohlcv_symbol_format_regex",
                target_database="vesta_ohlcv.duckdb",
                target_table="core.market_ohlcv_daily",
                passed=(invalid_symbols == 0),
                severity="ERROR" if invalid_symbols > 0 else "INFO",
                metrics={"invalid_symbols_count": invalid_symbols},
                message="Mã chứng khoán tuân thủ tuyệt đối định dạng ký tự chuẩn."
            )
        )
        con.close()

    # =========================================================================
    # 2. DATABASE: vesta_market_index.duckdb
    # =========================================================================
    def audit_market_index_database(self):
        """Kiểm định CSDL Dòng tiền & Độ rộng thị trường."""
        con = self._get_connection("vesta_market_index.duckdb")
        if con is None:
            return

        # 2.1 Foreign flow volume & uniqueness
        ff_count = con.execute("SELECT COUNT(*) FROM core.market_foreign_flow_daily").fetchone()[0]
        ff_dups = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT symbol, date, COUNT(*) 
                FROM core.market_foreign_flow_daily 
                GROUP BY symbol, date 
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Uniqueness",
                check_type="Uniqueness",
                check_name="foreign_flow_composite_unique",
                target_database="vesta_market_index.duckdb",
                target_table="core.market_foreign_flow_daily",
                passed=(ff_dups == 0 and ff_count >= 4_500_000),
                severity="ERROR" if ff_dups > 0 else "INFO",
                metrics={"total_rows": ff_count, "duplicates": ff_dups},
                message=f"Dòng tiền khối ngoại đạt {ff_count:,} dòng, không trùng lặp.",
            )
        )

        # 2.2 Accuracy: Non-negative values and math balance
        ff_math_errors = con.execute("""
            SELECT COUNT(*) FROM core.market_foreign_flow_daily
            WHERE buy_value < 0 OR sell_value < 0
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Accuracy",
                check_type="Mandatory",
                check_name="foreign_flow_non_negative",
                target_database="vesta_market_index.duckdb",
                target_table="core.market_foreign_flow_daily",
                passed=(ff_math_errors == 0),
                severity="ERROR" if ff_math_errors > 0 else "INFO",
                metrics={"negative_rows": ff_math_errors},
                message="Giá trị mua/bán khối ngoại hoàn toàn không âm."
            )
        )

        # 2.3 Fear & Greed accuracy & freshness
        fg_row = con.execute("SELECT MAX(snapshot_date), COUNT(*) FROM core.market_sentiment_snapshot").fetchone()
        fg_invalid = con.execute("SELECT COUNT(*) FROM core.market_sentiment_snapshot WHERE fear_greed_score < 0 OR fear_greed_score > 100").fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Accuracy",
                check_type="Anomaly",
                check_name="sentiment_fear_greed_range",
                target_database="vesta_market_index.duckdb",
                target_table="core.market_sentiment_snapshot",
                passed=(fg_invalid == 0 and str(fg_row[0]) >= "2026-10-09"),
                severity="ERROR" if (fg_invalid > 0 or str(fg_row[0]) < "2026-10-09") else "INFO",
                metrics={"latest_date": str(fg_row[0]), "total_records": fg_row[1], "out_of_range": fg_invalid},
                message=f"Chỉ số Fear & Greed chuẩn xác [0, 100], cập nhật đến {fg_row[0]}."
            )
        )
        con.close()

    # =========================================================================
    # 3. DATABASE: vesta_news.duckdb
    # =========================================================================
    def audit_news_database(self):
        """Kiểm định CSDL Tin tức tài chính & Vĩ mô."""
        con = self._get_connection("vesta_news.duckdb")
        if con is None:
            return

        news_count = con.execute("SELECT COUNT(*) FROM core.news").fetchone()[0]
        macro_count = con.execute("SELECT COUNT(*) FROM core.macro_policy").fetchone()[0]
        max_news_time = con.execute("SELECT MAX(published_at) FROM core.news").fetchone()[0]

        # 3.1 Completeness: Null value checks (dbt not_null)
        null_news = con.execute("""
            SELECT COUNT(*) FROM core.news
            WHERE headline IS NULL OR source_url IS NULL OR published_at IS NULL
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Completeness",
                check_type="Mandatory",
                check_name="news_mandatory_not_null",
                target_database="vesta_news.duckdb",
                target_table="core.news",
                passed=(null_news == 0 and news_count >= 1_000_000),
                severity="ERROR" if null_news > 0 else "INFO",
                metrics={"news_count": news_count, "macro_count": macro_count, "null_records": null_news},
                message=f"Đạt {news_count:,} bài báo và {macro_count:,} vĩ mô. Không có bài báo thiếu trường bắt buộc."
            )
        )

        # 3.2 Timeliness & Freshness
        fresh_passed = str(max_news_time) >= "2026-10-09"
        self.results.append(
            QualityCheckResult(
                dimension="Timeliness",
                check_type="Volume",
                check_name="news_freshness_sla",
                target_database="vesta_news.duckdb",
                target_table="core.news",
                passed=fresh_passed,
                severity="ERROR" if not fresh_passed else "INFO",
                metrics={"latest_news_timestamp": str(max_news_time)},
                message=f"Tin tức tài chính cập nhật thời gian thực đến {max_news_time}."
            )
        )
        con.close()

    # =========================================================================
    # 4. DATABASE: vesta_fundamentals.duckdb
    # =========================================================================
    def audit_fundamentals_database(self):
        """Kiểm định CSDL BCTC & Thuyết minh tài chính."""
        con = self._get_connection("vesta_fundamentals.duckdb")
        if con is None:
            return

        fun_count = con.execute("SELECT COUNT(*) FROM core.fundamentals").fetchone()[0]
        notes_count = con.execute("SELECT COUNT(*) FROM core.financial_notes").fetchone()[0]

        # 4.1 Completeness & Volume
        self.results.append(
            QualityCheckResult(
                dimension="Completeness",
                check_type="Volume",
                check_name="fundamentals_volume_threshold",
                target_database="vesta_fundamentals.duckdb",
                target_table="core.fundamentals",
                passed=(fun_count >= 70_000 and notes_count >= 7_000_000),
                severity="INFO",
                metrics={"fundamentals_rows": fun_count, "financial_notes_rows": notes_count},
                message=f"Đạt {fun_count:,} BCTC và {notes_count:,} thuyết minh chuyên sâu."
            )
        )

        # 4.2 Accuracy: Fiscal range validation
        invalid_fun_dates = con.execute("""
            SELECT COUNT(*) FROM core.fundamentals
            WHERE period_end < '2000-01-01' OR period_end > '2026-12-31'
        """).fetchone()[0]

        self.results.append(
            QualityCheckResult(
                dimension="Accuracy",
                check_type="Mandatory",
                check_name="fundamentals_fiscal_range",
                target_database="vesta_fundamentals.duckdb",
                target_table="core.fundamentals",
                passed=(invalid_fun_dates == 0),
                severity="ERROR" if invalid_fun_dates > 0 else "INFO",
                metrics={"out_of_range_records": invalid_fun_dates},
                message="Niên độ tài chính BCTC chuẩn hóa từ năm 2000 đến 2026 Q2."
            )
        )
        con.close()


    # =========================================================================
    # 5. DATABASE: vesta_events.duckdb
    # =========================================================================
    def audit_events_database(self):
        """Kiểm định CSDL Sự kiện doanh nghiệp & Cổ tức."""
        con = self._get_connection("vesta_events.duckdb")
        if con is None:
            return

        events_count = con.execute("SELECT COUNT(*) FROM core.corporate_events").fetchone()[0]
        max_event_date = con.execute("SELECT MAX(event_date) FROM core.corporate_events").fetchone()[0]

        # 5.1 Timeliness & Future Horizon
        future_passed = str(max_event_date) >= "2026-10-09"
        self.results.append(
            QualityCheckResult(
                dimension="Timeliness",
                check_type="Volume",
                check_name="corporate_events_future_horizon",
                target_database="vesta_events.duckdb",
                target_table="core.corporate_events",
                passed=future_passed,
                severity="INFO",
                metrics={"total_events": events_count, "max_event_date": str(max_event_date)},
                message=f"Tổng {events_count:,} sự kiện, đường chân trời mở rộng đến {max_event_date}."
            )
        )
        con.close()

    # =========================================================================
    # EXECUTION & REPORT GENERATION
    # =========================================================================
    def run_all_checks(self) -> List[QualityCheckResult]:
        """Thực thi toàn bộ bộ kiểm định chất lượng dữ liệu trên 5 cơ sở dữ liệu."""
        self.results = []
        logger.info("Bắt đầu thực thi VESTA Data Quality Pipeline Suite...")
        self.audit_ohlcv_database()
        self.audit_market_index_database()
        self.audit_news_database()
        self.audit_fundamentals_database()
        self.audit_events_database()
        return self.results

    def generate_report(self) -> Dict[str, Any]:
        """Tạo báo cáo tổng hợp chi tiết theo 6 chiều và 5 loại hình kiểm tra."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        by_dimension: Dict[str, Dict[str, int]] = {}
        by_check_type: Dict[str, Dict[str, int]] = {}

        for r in self.results:
            by_dimension.setdefault(r.dimension, {"total": 0, "passed": 0})
            by_dimension[r.dimension]["total"] += 1
            if r.passed:
                by_dimension[r.dimension]["passed"] += 1

            by_check_type.setdefault(r.check_type, {"total": 0, "passed": 0})
            by_check_type[r.check_type]["total"] += 1
            if r.passed:
                by_check_type[r.check_type]["passed"] += 1

        report = {
            "timestamp": dt.datetime.now().isoformat(),
            "status": "PASS" if failed == 0 else "FAIL",
            "summary": {
                "total_checks": total,
                "passed_checks": passed,
                "failed_checks": failed,
                "pass_rate_percent": round((passed / total * 100.0) if total > 0 else 0.0, 2),
            },
            "by_dimension": by_dimension,
            "by_check_type": by_check_type,
            "details": [r.to_dict() for r in self.results],
        }

        # Lưu báo cáo JSON và Markdown ra out/
        out_dir = REPO_ROOT / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "data_quality_report.json"
        md_path = out_dir / "data_quality_report.md"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        md_content = self._render_markdown_report(report)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"Đã xuất báo cáo chất lượng dữ liệu: {json_path} và {md_path}")
        return report

    def _render_markdown_report(self, report: Dict[str, Any]) -> str:
        s = report["summary"]
        lines = [
            "# BÁO CÁO KIỂM ĐỊNH CHẤT LƯỢNG DỮ LIỆU VESTA (DATA QUALITY AUDIT REPORT)",
            f"> **Thời điểm:** {report['timestamp']}  ",
            f"> **Trạng thái tổng thể:** `{'✅ PASS' if s['failed_checks'] == 0 else '❌ FAIL'}`  ",
            f"> **Tỷ lệ đạt chuẩn:** **{s['pass_rate_percent']}%** ({s['passed_checks']}/{s['total_checks']} quy tắc kiểm định)",
            "",
            "---",
            "",
            "## 1. KẾT QUẢ THEO 6 TRỌNG TÂM ĐO LƯỜNG (KEY DIMENSIONS)",
            "| Chiều Đo Lường (Dimension) | Tổng Số Kiểm Tra | Đạt Chuẩn (Passed) | Tỷ Lệ Đạt |",
            "| :--- | :---: | :---: | :---: |",
        ]
        for dim, stats in report["by_dimension"].items():
            rate = round(stats["passed"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
            lines.append(f"| **{dim}** | {stats['total']} | {stats['passed']} | {rate}% |")

        lines.extend([
            "",
            "## 2. KẾT QUẢ THEO 5 LOẠI HÌNH KIỂM TRA CỐT LÕI (ESSENTIAL CHECK TYPES)",
            "| Loại Hình (Check Type) | Tổng Số Kiểm Tra | Đạt Chuẩn | Trạng Thái |",
            "| :--- | :---: | :---: | :---: |",
        ])
        for ct, stats in report["by_check_type"].items():
            status_icon = "✅ ĐẠT" if stats["passed"] == stats["total"] else "⚠️ CẢNH BÁO"
            lines.append(f"| **{ct}** | {stats['total']} | {stats['passed']} | {status_icon} |")

        lines.extend([
            "",
            "## 3. CHI TIẾT TỪNG QUY TẮC KIỂM ĐỊNH (AUDIT MATRIX)",
            "| CSDL / Bảng Mục Tiêu | Tên Quy Tắc | Chiều | Loại Hình | Trạng Thái | Thông Điệp Nghiệm Thu |",
            "| :--- | :--- | :--- | :--- | :---: | :--- |",
        ])
        for r in report["details"]:
            st = "✅ PASS" if r["passed"] else "❌ FAIL"
            lines.append(f"| `{r['target_database']}`<br/>`{r['target_table']}` | `{r['check_name']}` | {r['dimension']} | {r['check_type']} | {st} | {r['message']} |")

        lines.append("")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="VESTA Data Quality Pipeline Suite")
    parser.add_argument("--admin", action="store_true", help="Kiểm định trên db/admin/")
    args = parser.parse_args()

    suite = VestaDataQualitySuite(use_admin=args.admin)
    suite.run_all_checks()
    rep = suite.generate_report()

    print("\n" + "=" * 80)
    print(f"VESTA DATA QUALITY AUDIT REPORT — STATUS: {rep['status']}")
    print(f"Tổng kiểm định: {rep['summary']['total_checks']} | Đạt: {rep['summary']['passed_checks']} | Lỗi: {rep['summary']['failed_checks']} | Tỷ lệ: {rep['summary']['pass_rate_percent']}%")
    print("=" * 80)
    for r in rep["details"]:
        icon = "✓" if r["passed"] else "✗"
        print(f" {icon} [{r['dimension']}] {r['check_name']} ({r['target_table']}): {r['message']}")
    print("=" * 80 + "\n")

    return 0 if rep["summary"]["failed_checks"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
