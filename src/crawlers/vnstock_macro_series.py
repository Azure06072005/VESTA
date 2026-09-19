"""src/crawlers/vnstock_macro_series.py

Crawler & Ingester cho trọn bộ 9 chỉ số Kinh tế Vĩ mô từ Vnstock:
1. gdp (Tổng sản phẩm quốc nội - Nông nghiệp, Công nghiệp, Dịch vụ, Thuế, GDP)
2. cpi (Chỉ số giá tiêu dùng - CPI tổng hợp, CPI cốt lõi)
3. fdi (Đầu tư trực tiếp nước ngoài - Vốn đăng ký, Vốn thực hiện)
4. interest_rate (Lãi suất liên ngân hàng - ON, 1W, 2W, 1M, 3M, 6M, 9M, 1Y) -> nạp cả core.macro_rates
5. import_export (Kim ngạch xuất nhập khẩu - Xuất khẩu, Nhập khẩu, Cán cân)
6. money_supply (Cung tiền M2 - Tổng phương tiện thanh toán, Tổ chức kinh tế, Dân cư)
7. exchange_rate (Tỷ giá USD/VND - Trung tâm, Vietcombank, Thị trường tự do) -> nạp cả core.macro_rates
8. retail (Tổng mức bán lẻ hàng hóa và doanh thu dịch vụ tiêu dùng)
9. industry_prod (Chỉ số sản xuất công nghiệp IIP theo nhóm ngành)

Điểm đến:
- core.macro_rates: rate_type, term, date, rate_value, source, fetched_at
- core.macro_economic_series: indicator, sub_indicator, report_period, period_date, numeric_value, unit, meta_json, source, fetched_at
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

# Thêm root dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.crawlers.db_writer import ResilientDuckDBWriter
from vnstock_data import Macro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawlers.vnstock_macro_series")


class VnstockMacroSeriesCrawler:
    """Bộ thu thập và chuẩn hóa trọn bộ 9 chỉ số kinh tế vĩ mô từ Vnstock."""

    def __init__(self, writer: Optional[ResilientDuckDBWriter] = None) -> None:
        self.writer = writer or ResilientDuckDBWriter()
        self.macro = Macro()

    def _save_series(self, df_series: pd.DataFrame, indicator_name: str) -> int:
        """Lưu trữ chuỗi vĩ mô chuẩn hóa vào staging và core.macro_economic_series."""
        if df_series is None or df_series.empty:
            logger.info("Chỉ số %s không có dữ liệu mới.", indicator_name)
            return 0

        now = dt.datetime.now(dt.timezone.utc)
        required_cols = [
            "indicator", "sub_indicator", "report_period", "period_date",
            "numeric_value", "unit", "meta_json", "source", "fetched_at"
        ]

        # Đảm bảo đủ các cột
        for col in required_cols:
            if col not in df_series.columns:
                if col == "source":
                    df_series[col] = "vnstock"
                elif col == "fetched_at":
                    df_series[col] = now
                else:
                    df_series[col] = None

        df_to_save = df_series[required_cols].copy()

        def _insert_macro(con: duckdb.DuckDBPyConnection) -> int:
            con.register("df_macro_staging", df_to_save)
            con.execute("""
                INSERT INTO staging.macro_economic_series
                SELECT * FROM df_macro_staging
            """)
            con.unregister("df_macro_staging")

            con.register("df_macro_core", df_to_save)
            con.execute("""
                INSERT INTO core.macro_economic_series
                SELECT * FROM df_macro_core
                ON CONFLICT (indicator, sub_indicator, report_period) DO UPDATE SET
                    period_date = EXCLUDED.period_date,
                    numeric_value = EXCLUDED.numeric_value,
                    unit = EXCLUDED.unit,
                    meta_json = EXCLUDED.meta_json,
                    fetched_at = EXCLUDED.fetched_at
            """)
            con.unregister("df_macro_core")
            return len(df_to_save)

        count = self.writer.execute_with_retry(_insert_macro)
        logger.info("-> [%s] Đã lưu +%d dòng vào core.macro_economic_series", indicator_name, count)
        return count

    def _save_rates(self, df_rates: pd.DataFrame, rate_type: str) -> int:
        """Lưu trữ lãi suất/tỷ giá vào staging và core.macro_rates."""
        if df_rates is None or df_rates.empty:
            return 0

        now = dt.datetime.now(dt.timezone.utc)
        required_cols = ["rate_type", "term", "date", "rate_value", "source", "fetched_at"]
        for col in required_cols:
            if col not in df_rates.columns:
                if col == "source":
                    df_rates[col] = "vnstock"
                elif col == "fetched_at":
                    df_rates[col] = now
                else:
                    df_rates[col] = None

        df_to_save = df_rates[required_cols].dropna(subset=["term", "date", "rate_value"]).copy()

        def _insert_rates(con: duckdb.DuckDBPyConnection) -> int:
            con.register("df_rates_staging", df_to_save)
            con.execute("""
                INSERT INTO staging.macro_rates
                SELECT * FROM df_rates_staging
            """)
            con.unregister("df_rates_staging")

            con.register("df_rates_core", df_to_save)
            con.execute("""
                INSERT INTO core.macro_rates
                SELECT * FROM df_rates_core
                ON CONFLICT (rate_type, term, date) DO UPDATE SET
                    rate_value = EXCLUDED.rate_value,
                    source = EXCLUDED.source,
                    fetched_at = EXCLUDED.fetched_at
            """)
            con.unregister("df_rates_core")
            return len(df_to_save)

        count = self.writer.execute_with_retry(_insert_rates)
        logger.info("-> [%s] Đã lưu +%d dòng vào core.macro_rates", rate_type, count)
        return count

    def crawl_gdp(self) -> int:
        """Thu thập chỉ số GDP theo ngành."""
        logger.info("Bắt đầu cào chỉ số GDP...")
        df = self.macro.economy().gdp()
        if df is None or df.empty:
            return 0

        records = []
        now = dt.datetime.now(dt.timezone.utc)
        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            for col in ["agriculture", "industry", "services", "tax", "gdp", "vnindex"]:
                if col in row and pd.notnull(row[col]):
                    records.append({
                        "indicator": "gdp",
                        "sub_indicator": col,
                        "report_period": p_str,
                        "period_date": p_date,
                        "numeric_value": float(row[col]),
                        "unit": "%" if "growth" in col or col == "gdp" else "VND/Index",
                        "meta_json": None,
                        "source": "vnstock",
                        "fetched_at": now,
                    })
        return self._save_series(pd.DataFrame(records), "gdp")

    def crawl_cpi(self) -> int:
        """Thu thập chỉ số giá tiêu dùng CPI."""
        logger.info("Bắt đầu cào chỉ số CPI...")
        df = self.macro.economy().cpi()
        if df is None or df.empty:
            return 0

        records = []
        now = dt.datetime.now(dt.timezone.utc)
        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            for col in ["cpi_total", "cpi_core", "vnindex"]:
                if col in row and pd.notnull(row[col]):
                    records.append({
                        "indicator": "cpi",
                        "sub_indicator": col,
                        "report_period": p_str,
                        "period_date": p_date,
                        "numeric_value": float(row[col]),
                        "unit": "%" if "cpi" in col else "Index",
                        "meta_json": None,
                        "source": "vnstock",
                        "fetched_at": now,
                    })
        return self._save_series(pd.DataFrame(records), "cpi")

    def crawl_fdi(self) -> int:
        """Thu thập dòng vốn đầu tư trực tiếp nước ngoài FDI."""
        logger.info("Bắt đầu cào chỉ số FDI...")
        df = self.macro.economy().fdi()
        if df is None or df.empty:
            return 0

        records = []
        now = dt.datetime.now(dt.timezone.utc)
        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            for col in ["register_value", "realized_value", "realized_percent"]:
                if col in row and pd.notnull(row[col]):
                    records.append({
                        "indicator": "fdi",
                        "sub_indicator": col,
                        "report_period": p_str,
                        "period_date": p_date,
                        "numeric_value": float(row[col]),
                        "unit": "%" if "percent" in col else "Million USD",
                        "meta_json": None,
                        "source": "vnstock",
                        "fetched_at": now,
                    })
        return self._save_series(pd.DataFrame(records), "fdi")

    def crawl_interest_rate(self) -> int:
        """Thu thập lãi suất liên ngân hàng và chính sách."""
        logger.info("Bắt đầu cào chỉ số Lãi suất (Interest Rates)...")
        df = self.macro.currency().interest_rate()
        if df is None or df.empty:
            return 0

        records_series = []
        records_rates = []
        now = dt.datetime.now(dt.timezone.utc)

        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            val = float(row["value"]) if pd.notnull(row.get("value")) else None
            if val is None:
                continue

            grp = str(row.get("group_name", "INTERBANK"))
            term_name = str(row.get("name", "N/A"))
            unit_str = str(row.get("unit", "%"))

            # 1. Thêm vào bảng series
            records_series.append({
                "indicator": "interest_rate",
                "sub_indicator": f"{grp}:{term_name}",
                "report_period": p_str,
                "period_date": p_date,
                "numeric_value": val,
                "unit": unit_str,
                "meta_json": json.dumps({"source_agency": str(row.get("source", ""))}),
                "source": "vnstock",
                "fetched_at": now,
            })

            # 2. Thêm vào bảng core.macro_rates
            records_rates.append({
                "rate_type": grp,
                "term": term_name,
                "date": p_date,
                "rate_value": val,
                "source": "vnstock",
                "fetched_at": now,
            })

        c_series = self._save_series(pd.DataFrame(records_series), "interest_rate")
        self._save_rates(pd.DataFrame(records_rates), "INTERBANK")
        return c_series

    def crawl_import_export(self) -> int:
        """Thu thập cán cân Xuất nhập khẩu."""
        logger.info("Bắt đầu cào chỉ số Xuất Nhập Khẩu...")
        df = self.macro.economy().import_export()
        if df is None or df.empty:
            return 0

        records = []
        now = dt.datetime.now(dt.timezone.utc)
        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            for col in ["export_value", "import_value", "balance_value", "export_growth", "import_growth"]:
                if col in row and pd.notnull(row[col]):
                    records.append({
                        "indicator": "import_export",
                        "sub_indicator": col,
                        "report_period": p_str,
                        "period_date": p_date,
                        "numeric_value": float(row[col]),
                        "unit": "%" if "growth" in col else "Million USD",
                        "meta_json": None,
                        "source": "vnstock",
                        "fetched_at": now,
                    })
        return self._save_series(pd.DataFrame(records), "import_export")

    def crawl_money_supply(self) -> int:
        """Thu thập cung tiền M2."""
        logger.info("Bắt đầu cào chỉ số Cung tiền M2...")
        df = self.macro.economy().money_supply()
        if df is None or df.empty:
            return 0

        records = []
        now = dt.datetime.now(dt.timezone.utc)
        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            for col in ["total", "institutional", "private", "vnindex"]:
                if col in row and pd.notnull(row[col]):
                    records.append({
                        "indicator": "money_supply",
                        "sub_indicator": col,
                        "report_period": p_str,
                        "period_date": p_date,
                        "numeric_value": float(row[col]),
                        "unit": "Billion VND" if col != "vnindex" else "Index",
                        "meta_json": None,
                        "source": "vnstock",
                        "fetched_at": now,
                    })
        return self._save_series(pd.DataFrame(records), "money_supply")

    def crawl_exchange_rate(self) -> int:
        """Thu thập tỷ giá ngoại hối USD/VND."""
        logger.info("Bắt đầu cào chỉ số Tỷ giá ngoại hối...")
        df = self.macro.currency().exchange_rate()
        if df is None or df.empty:
            return 0

        records_series = []
        records_rates = []
        now = dt.datetime.now(dt.timezone.utc)

        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            for col in ["center_rate", "vcb_rate", "market_rate", "vnindex"]:
                if col in row and pd.notnull(row[col]):
                    val = float(row[col])
                    records_series.append({
                        "indicator": "exchange_rate",
                        "sub_indicator": col,
                        "report_period": p_str,
                        "period_date": p_date,
                        "numeric_value": val,
                        "unit": "VND/USD" if col != "vnindex" else "Index",
                        "meta_json": None,
                        "source": "vnstock",
                        "fetched_at": now,
                    })
                    if col != "vnindex":
                        records_rates.append({
                            "rate_type": "EXCHANGE_RATE",
                            "term": col.upper(),
                            "date": p_date,
                            "rate_value": val,
                            "source": "vnstock",
                            "fetched_at": now,
                        })

        c_series = self._save_series(pd.DataFrame(records_series), "exchange_rate")
        self._save_rates(pd.DataFrame(records_rates), "EXCHANGE_RATE")
        return c_series

    def crawl_retail(self) -> int:
        """Thu thập chỉ số bán lẻ tiêu dùng."""
        logger.info("Bắt đầu cào chỉ số Bán lẻ...")
        df = self.macro.economy().retail()
        if df is None or df.empty:
            return 0

        records = []
        now = dt.datetime.now(dt.timezone.utc)
        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            name = str(row.get("name", "RETAIL_TOTAL"))
            val = float(row["value"]) if pd.notnull(row.get("value")) else None
            if val is not None:
                records.append({
                    "indicator": "retail",
                    "sub_indicator": name,
                    "report_period": p_str,
                    "period_date": p_date,
                    "numeric_value": val,
                    "unit": str(row.get("unit", "Billion VND")),
                    "meta_json": json.dumps({"source": str(row.get("source", ""))}),
                    "source": "vnstock",
                    "fetched_at": now,
                })
        return self._save_series(pd.DataFrame(records), "retail")

    def crawl_industry_prod(self) -> int:
        """Thu thập chỉ số sản xuất công nghiệp IIP."""
        logger.info("Bắt đầu cào chỉ số Sản xuất công nghiệp IIP...")
        df = self.macro.economy().industry_prod()
        if df is None or df.empty:
            return 0

        records = []
        now = dt.datetime.now(dt.timezone.utc)
        for _, row in df.iterrows():
            t = pd.to_datetime(row["time"])
            p_str = t.strftime("%Y-%m-%d")
            p_date = t.date()
            grp = str(row.get("group_name", ""))
            name = str(row.get("name", "IIP_INDEX"))
            sub_name = f"{grp}:{name}" if grp else name
            val = float(row["value"]) if pd.notnull(row.get("value")) else None
            if val is not None:
                records.append({
                    "indicator": "industry_prod",
                    "sub_indicator": sub_name,
                    "report_period": p_str,
                    "period_date": p_date,
                    "numeric_value": val,
                    "unit": str(row.get("unit", "%")),
                    "meta_json": json.dumps({"source": str(row.get("source", ""))}),
                    "source": "vnstock",
                    "fetched_at": now,
                })
        return self._save_series(pd.DataFrame(records), "industry_prod")

    def crawl_all(self) -> Dict[str, int]:
        """Thực thi toàn bộ 9 chỉ số vĩ mô."""
        logger.info("=== BẮT ĐẦU CÀO TRỌN BỘ 9 CHỈ SỐ VĨ MÔ VNSTOCK ===")
        results = {}
        indicators = [
            ("gdp", self.crawl_gdp),
            ("cpi", self.crawl_cpi),
            ("fdi", self.crawl_fdi),
            ("interest_rate", self.crawl_interest_rate),
            ("import_export", self.crawl_import_export),
            ("money_supply", self.crawl_money_supply),
            ("exchange_rate", self.crawl_exchange_rate),
            ("retail", self.crawl_retail),
            ("industry_prod", self.crawl_industry_prod),
        ]
        for name, fn in indicators:
            try:
                results[name] = fn()
            except Exception as e:
                logger.error("Lỗi khi cào chỉ số vĩ mô %s: %s", name, e)
                results[name] = 0

        total = sum(results.values())
        logger.info("=== HOÀN TẤT CÀO VĨ MÔ: Tổng cộng +%d bản ghi ===", total)
        return results


def main() -> None:
    """CLI entrypoint cho bộ cào vĩ mô."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Vnstock Macroeconomic 9 Indicators Crawler")
    parser.add_argument("--indicators", default="all", help="Danh sách chỉ số cần cào (all hoặc gdp,cpi...)")
    args = parser.parse_args()

    crawler = VnstockMacroSeriesCrawler()
    if args.indicators == "all":
        res = crawler.crawl_all()
    else:
        chosen = [x.strip() for x in args.indicators.split(",")]
        res = {}
        for c in chosen:
            fn = getattr(crawler, f"crawl_{c}", None)
            if fn:
                res[c] = fn()
            else:
                logger.warning("Không tìm thấy chỉ số: %s", c)

    print("\n=== KẾT QUẢ CÀO VĨ MÔ VNSTOCK ===")
    for k, v in res.items():
        print(f"  {k:20s}: {v:6d} bản ghi")


if __name__ == "__main__":
    main()
