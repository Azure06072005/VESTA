"""World Bank Open Data Macroeconomic Crawler for Vietnam.

Thu thập các chỉ báo kinh tế vĩ mô chính thức của Việt Nam từ REST API công khai
của Ngân hàng Thế giới (World Bank) nhằm phục vụ mô hình phân loại chu kỳ vĩ mô (Macro Regime).
Lưu trữ vào `core.macro_policy` với khóa chính `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

# Danh mục các chỉ số vĩ mô cốt lõi cho thị trường Việt Nam
WORLDBANK_INDICATORS: dict[str, dict[str, str]] = {
    "NY.GDP.MKTP.KD.ZG": {
        "name": "Tăng trưởng GDP thực tế hàng năm (GDP growth annual %)",
        "unit": "%",
        "category": "Tăng trưởng kinh tế",
    },
    "FP.CPI.TOTL.ZG": {
        "name": "Tỷ lệ lạm phát chỉ số giá tiêu dùng (Inflation, consumer prices annual %)",
        "unit": "%",
        "category": "Lạm phát & Giá cả",
    },
    "BX.KLT.DINV.WD.GD.ZS": {
        "name": "Vốn đầu tư trực tiếp nước ngoài FDI ròng (FDI net inflows % of GDP)",
        "unit": "% GDP",
        "category": "Đầu tư quốc tế",
    },
    "NE.EXP.GNFS.ZS": {
        "name": "Xuất khẩu hàng hóa và dịch vụ (Exports of goods and services % of GDP)",
        "unit": "% GDP",
        "category": "Ngoại thương",
    },
    "NE.IMP.GNFS.ZS": {
        "name": "Nhập khẩu hàng hóa và dịch vụ (Imports of goods and services % of GDP)",
        "unit": "% GDP",
        "category": "Ngoại thương",
    },
    "FR.INR.LNDP": {
        "name": "Mặt bằng lãi suất cho vay bình quân (Lending interest rate %)",
        "unit": "%",
        "category": "Tiền tệ & Lãi suất",
    },
}

API_BASE = "https://api.worldbank.org/v2/country/VNM/indicator"


def fetch_indicator_series(indicator_code: str, per_page: int = 50) -> list[dict[str, Any]]:
    """Gọi World Bank REST API lấy chuỗi thời gian cho 1 chỉ số của Việt Nam."""
    url = f"{API_BASE}/{indicator_code}?format=json&per_page={per_page}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Lỗi API World Bank {indicator_code}: HTTP {resp.status_code}")
            return []
        data = resp.json()
        if len(data) > 1 and isinstance(data[1], list):
            return data[1]
    except Exception as e:
        logger.error(f"Lỗi kết nối World Bank {indicator_code}: {e}")
    return []


def transform_wb_record(raw: dict[str, Any], indicator_code: str, meta: dict[str, str]) -> dict[str, Any] | None:
    """Chuẩn hóa một bản ghi World Bank thành cấu trúc core.macro_policy."""
    val = raw.get("value")
    year_str = raw.get("date")
    if val is None or not year_str:
        return None

    try:
        year = int(year_str)
    except ValueError:
        return None

    # Công bố chính thức chỉ số năm thường diễn ra vào cuối năm hoặc đầu năm sau
    # Để an toàn cho backtest, đặt available_at vào ngày 31/12 của năm thống kê
    pub_date = dt.datetime(year, 12, 31, 0, 0, 0)

    val_fmt = f"{val:.2f}" if isinstance(val, (int, float)) else str(val)
    headline = f"[World Bank] {meta['name']} năm {year}: {val_fmt}{meta['unit']}"
    summary = f"Chỉ số vĩ mô Việt Nam được công bố bởi Ngân hàng Thế giới (World Bank). Phân loại: {meta['category']}."
    body = (
        f"Chỉ số: {meta['name']} (Mã WB: {indicator_code})\n"
        f"Quốc gia: Việt Nam (VNM)\n"
        f"Năm thống kê: {year}\n"
        f"Giá trị ghi nhận: {val_fmt} {meta['unit']}\n"
        f"Phân loại vĩ mô: {meta['category']}\n"
        f"Nguồn dữ liệu: World Bank Open Data REST API (api.worldbank.org)"
    )
    source_url = f"https://data.worldbank.org/indicator/{indicator_code}?locations=VN&year={year}"

    return {
        "source": "worldbank",
        "issuing_body": "World Bank (Ngân hàng Thế giới)",
        "doc_type": "macro_indicator",
        "doc_number": indicator_code,
        "published_at": pub_date,
        "available_at": pub_date,
        "headline": headline,
        "summary": summary,
        "body": body,
        "source_url": source_url,
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    }


class WorldBankCrawler:
    """Trình thu thập dữ liệu vĩ mô Việt Nam từ World Bank API."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb"):
        self.duckdb_path = duckdb_path

    def save_batch(self, records: list[dict[str, Any]]) -> int:
        """Lưu danh sách chỉ số vào DuckDB core.macro_policy."""
        if not records:
            return 0
        df = pd.DataFrame(records)
        for attempt in range(6):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=False)
                con.register("df_wb_batch", df)
                con.execute("""
                    INSERT INTO core.macro_policy (
                        source, issuing_body, doc_type, doc_number,
                        published_at, available_at, headline, summary,
                        body, source_url, fetched_at
                    )
                    SELECT
                        source, issuing_body, doc_type, doc_number,
                        published_at, available_at, headline, summary,
                        body, source_url, fetched_at
                    FROM df_wb_batch
                    ON CONFLICT (source_url) DO UPDATE SET
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        body = EXCLUDED.body,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.close()
                return len(df)
            except Exception as e:
                time.sleep((attempt + 1) * 1.5)
        return len(df)

    def crawl(self, indicators: list[str] | None = None, dry_run: bool = False) -> int:
        """Cào toàn bộ các chỉ số đã định nghĩa."""
        target_keys = indicators or list(WORLDBANK_INDICATORS.keys())
        total_ingested = 0

        for ind_code in target_keys:
            meta = WORLDBANK_INDICATORS.get(ind_code)
            if not meta:
                continue

            logger.info(f"==> Đang tải World Bank Indicator: [{ind_code}] {meta['name']}...")
            raw_series = fetch_indicator_series(ind_code)
            records = []
            for r in raw_series:
                rec = transform_wb_record(r, ind_code, meta)
                if rec:
                    records.append(rec)

            if records:
                if not dry_run:
                    self.save_batch(records)
                total_ingested += len(records)
                logger.info(f"  -> [OK] Đã lưu {len(records)} năm số liệu cho {ind_code}.")
            time.sleep(0.5)

        logger.info(f"==> Hoàn thành: Đã lưu tổng cộng {total_ingested} bản ghi vĩ mô World Bank.")
        return total_ingested


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="World Bank Vietnam Macro Crawler")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    crawler = WorldBankCrawler()
    n = crawler.crawl(dry_run=args.dry_run)
    print(f"Tổng số bản ghi World Bank: {n}")


if __name__ == "__main__":
    main()
