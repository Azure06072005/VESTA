"""CafeF Finance Enhancer (apiweb.cafef.vn/api/v2/BCTC).

Thu thập Báo cáo tài chính doanh nghiệp chuyên sâu từ hệ thống API CafeF:
- Bảng Cân đối kế toán (GetReportCDKT)
- Báo cáo Kết quả hoạt động kinh doanh (GetReportDetail - KQKD)
- Báo cáo Lưu chuyển tiền tệ (GetReportLCTT)
- Chỉ số tài chính chuyên sâu (FinancialIndicators)

Lưu trữ vào:
- `core.fundamentals` (symbol, report_type, period_end, available_at, data_json, fetched_at)
Tuân thủ Zero Look-Ahead Bias: `available_at` = period_end + 30 ngày (Thông tư 96/2020/TT-BTC).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db
from etl.retry_failed_jobs import EmptyResultError

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-CafeF-Enhancer)"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://cafef.vn",
    "Referer": "https://cafef.vn/",
}

BASE_API_URL = "https://apiweb.cafef.vn"
DISCLOSURE_LAG_DAYS = 30  # Thông tư 96/2020/TT-BTC


class CafeFFinanceEnhancer:
    """Bộ thu thập Báo cáo tài chính chuẩn xác từ CafeF Web API."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb", delay: float = 0.8) -> None:
        self.duckdb_path = duckdb_path
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._init_schema()

    def _init_schema(self) -> None:
        """Khởi tạo bảng core.fundamentals nếu chưa có."""
        try:
            con = duckdb.connect(self.duckdb_path, read_only=False)
            con.execute("CREATE SCHEMA IF NOT EXISTS core;")
            con.execute("""
                CREATE TABLE IF NOT EXISTS core.fundamentals (
                    symbol VARCHAR NOT NULL,
                    report_type VARCHAR NOT NULL,
                    period_end DATE NOT NULL,
                    available_at TIMESTAMP NOT NULL,
                    data_json JSON NOT NULL,
                    fetched_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, report_type, period_end)
                );
            """)
            con.close()
        except Exception as e:
            logger.warning(f"Lỗi khởi tạo bảng core.fundamentals: {e}")

    @staticmethod
    def _parse_quarter_period(period_str: str) -> dt.date | None:
        """Chuyển chuỗi kỳ hạn (ví dụ 'Q2/2026' hoặc '2026') thành ngày kết thúc quý period_end."""
        period_str = period_str.strip()
        m_q = re.match(r"^Q([1-4])[/_-](\d{4})$", period_str, re.IGNORECASE)
        if m_q:
            q = int(m_q.group(1))
            year = int(m_q.group(2))
            month_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[q]
            return dt.date(year, month_end[0], month_end[1])

        m_y = re.match(r"^(\d{4})$", period_str)
        if m_y:
            year = int(m_y.group(1))
            return dt.date(year, 12, 31)

        return None

    def fetch_report(self, symbol: str, report_type: str, type_time: str = "QUY", page_size: int = 4) -> dict[str, Any]:
        """Gửi request tới CafeF API theo từng loại báo cáo."""
        symbol = symbol.upper()
        if report_type == "balance_sheet":
            url = f"{BASE_API_URL}/api/v2/BCTC/GetReportCDKT"
            params = {"symbol": symbol, "pageIndex": 1, "pageSize": page_size, "reportType": "ALL", "TypeTime": type_time}
        elif report_type == "income_statement":
            url = f"{BASE_API_URL}/api/v1/BCTC/GetReportDetail"
            params = {"symbol": symbol, "pageIndex": 1, "pageSize": page_size, "reportType": "KQKD", "TypeTime": type_time}
        elif report_type == "cash_flow":
            url = f"{BASE_API_URL}/api/v1/BCTC/GetReportLCTT"
            params = {"symbol": symbol, "pageIndex": 1, "pageSize": page_size, "reportType": "ALL", "TypeTime": type_time}
        elif report_type == "ratio":
            url = f"{BASE_API_URL}/api/v2/BCTC/FinancialIndicators"
            params = {"symbol": symbol, "pageIndex": 1, "pageSize": page_size}
        else:
            raise ValueError(f"Không hỗ trợ report_type: {report_type}")

        resp = self.session.get(url, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("isSuccess"):
            raise RuntimeError(f"CafeF API trả về lỗi cho {symbol} ({report_type}): {data.get('errors')}")

        return data.get("value", {})

    def parse_and_normalize(self, symbol: str, report_type: str, raw_value: dict[str, Any]) -> list[dict[str, Any]]:
        """Chuẩn hóa dữ liệu JSON thành các dòng record độc lập theo từng kỳ period_end."""
        rows: list[dict[str, Any]] = []
        now = dt.datetime.now(dt.timezone.utc)

        # Mapping code -> Tên chỉ tiêu từ 'templace'
        template_list = raw_value.get("templace", []) or []
        code_to_name: dict[str, str] = {}
        for t in template_list:
            c = str(t.get("code", "")).strip()
            n = t.get("name", "").strip()
            if c and n:
                code_to_name[c] = n

        raw_data = raw_value.get("data", []) or []
        # Nếu là cấu trúc phân mục (CDKT, LCTT gồm Tài sản / Nguồn vốn...), gộp các mục theo từng kỳ
        if (
            raw_data
            and isinstance(raw_data[0], dict)
            and "data" in raw_data[0]
            and isinstance(raw_data[0]["data"], list)
            and raw_data[0]["data"]
            and isinstance(raw_data[0]["data"][0], dict)
            and "time" in raw_data[0]["data"][0]
        ):
            periods_by_time: dict[str, dict[str, Any]] = {}
            for section in raw_data:
                for sub_p in section.get("data", []):
                    t = sub_p.get("time")
                    if not t:
                        continue
                    if t not in periods_by_time:
                        periods_by_time[t] = {
                            "year": sub_p.get("year"),
                            "quater": sub_p.get("quater", 0),
                            "time": t,
                            "data": [],
                        }
                    periods_by_time[t]["data"].extend(sub_p.get("data", []))
            data_periods = list(periods_by_time.values())
        else:
            data_periods = raw_data

        for p_item in data_periods:
            year = p_item.get("year")
            quarter = p_item.get("quater", 0)
            time_str = p_item.get("time", "")

            # Xác định ngày kết thúc kỳ báo cáo
            if quarter and quarter in [1, 2, 3, 4] and year:
                month_end = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[quarter]
                p_date = dt.date(year, month_end[0], month_end[1])
            elif year:
                p_date = dt.date(year, 12, 31)
            else:
                p_date = self._parse_quarter_period(time_str)

            if not p_date:
                continue

            metrics: dict[str, Any] = {}
            metric_list = p_item.get("data", []) or []
            for m in metric_list:
                c = str(m.get("code", "")).strip()
                v = m.get("value")
                metric_name = code_to_name.get(c, m.get("name") or c)
                if metric_name:
                    metrics[metric_name] = v

            if not metrics:
                continue

            avail_at = dt.datetime.combine(
                p_date + dt.timedelta(days=DISCLOSURE_LAG_DAYS),
                dt.time(0, 0, 0),
                tzinfo=dt.timezone.utc
            )
            rows.append({
                "symbol": symbol.upper(),
                "report_type": report_type,
                "period_end": p_date,
                "available_at": avail_at,
                "data_json": json.dumps(metrics, ensure_ascii=False),
                "fetched_at": now,
            })

        return rows

    def save_batch(self, records: list[dict[str, Any]]) -> int:
        """Ghi batch bản ghi vào core.fundamentals qua write_statements tuân thủ append-only revision."""
        if not records:
            return 0

        df = pd.DataFrame(records)
        max_retries = 5
        retry_delay = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=False)
                from crawlers import fundamentals
                written = fundamentals.write_statements(df, con=con)
                con.close()
                return written
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"Lỗi lưu batch BCTC sau {max_retries} lần thử: {e}")
                    raise
                time.sleep(retry_delay * attempt)
        return 0

    def crawl_symbol(self, symbol: str) -> int:
        """Cào trọn gói 4 báo cáo tài chính cho 1 mã cổ phiếu."""
        total = 0
        for rtype in ["balance_sheet", "income_statement", "cash_flow", "ratio"]:
            try:
                raw_val = self.fetch_report(symbol, rtype)
                records = self.parse_and_normalize(symbol, rtype, raw_val)
                cnt = self.save_batch(records)
                total += cnt
                time.sleep(self.delay)
            except Exception as e:
                logger.warning(f"Không thể cào {rtype} cho {symbol}: {e}")
        return total


def get_all_symbols(duckdb_path: str = "d:/VESTA/db/vesta.duckdb") -> list[str]:
    """Lấy danh sách tất cả cổ phiếu 3 ký tự, sắp xếp theo thanh khoản 2026 giảm dần."""
    try:
        con = duckdb.connect(duckdb_path, read_only=True)
        query = """
            SELECT s.symbol, COALESCE(SUM(o.volume), 0) as vol_2026
            FROM core.dim_symbol s
            LEFT JOIN core.market_ohlcv_daily o ON s.symbol = o.symbol AND o.date >= '2026-01-01'
            WHERE length(s.symbol) = 3
            GROUP BY s.symbol
            ORDER BY vol_2026 DESC
        """
        rows = con.execute(query).fetchall()
        con.close()
        return [r[0] for r in rows]
    except Exception as e:
        logger.warning(f"Lỗi truy vấn danh sách mã: {e}")
        return ["VCB", "FPT", "HPG", "VHM", "VIC", "MWG", "TCB", "MBB", "ACB", "STB"]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="CafeF Finance Enhancer (Financial Statements BCTC)")
    parser.add_argument("--all", action="store_true", help="Cào toàn bộ toàn thị trường (1,751 mã cổ phiếu)")
    parser.add_argument("--symbols", nargs="+", default=None, help="Danh sách mã cổ phiếu cụ thể")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số mã cần cào")
    parser.add_argument("--start-idx", type=int, default=0, help="Chỉ số mã bắt đầu (cho phân trang / resume)")
    parser.add_argument("--delay", type=float, default=0.6, help="Độ trễ giữa các request (giây)")

    args = parser.parse_args()
    enhancer = CafeFFinanceEnhancer(delay=args.delay)

    if args.all or not args.symbols:
        target_symbols = get_all_symbols(enhancer.duckdb_path)
    else:
        target_symbols = args.symbols

    if args.start_idx > 0:
        target_symbols = target_symbols[args.start_idx:]

    if args.limit:
        target_symbols = target_symbols[:args.limit]

    logger.info(f"==> Bắt đầu nạp BCTC CafeF cho {len(target_symbols)} mã cổ phiếu (Delay: {args.delay}s)...")
    total_saved = 0
    for idx, s in enumerate(target_symbols, 1):
        try:
            cnt = enhancer.crawl_symbol(s)
            total_saved += cnt
            logger.info(f"[{idx}/{len(target_symbols)}] {s}: +{cnt} kỳ BCTC (Tổng: {total_saved})")
        except Exception as e:
            logger.error(f"[{idx}/{len(target_symbols)}] Lỗi cào mã {s}: {e}")

    print(f"\n==> Hoàn tất! Tổng số bản ghi BCTC đã nạp vào core.fundamentals: {total_saved}")


if __name__ == "__main__":
    main()
