"""Vietstock Finance Enhancer (finance.vietstock.vn).

Thu thập dữ liệu định lượng chuyên sâu từ Vietstock Finance:
- Báo cáo phân tích doanh nghiệp từ các CTCK (VPBankS, SSI, VNDirect, SSI, HSC, Mirae Asset...).
- Khuyến nghị đầu tư (MUA, BÁN, THEO DÕI, KHẢ QUAN, TRUNG LẬP).
- Giá mục tiêu (Target Price), Tỷ lệ sinh lời kỳ vọng (Upside %).
- File PDF báo cáo phân tích đính kèm.

Lưu trữ vào:
- `core.stock_research_reports` (primary key: `report_url`)
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
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://finance.vietstock.vn"
REPORT_PAGE_URL = "https://finance.vietstock.vn/bao-cao-phan-tich/phan-tich-doanh-nghiep"
AJAX_REPORT_URL = "https://finance.vietstock.vn/View/ChannelEDocumentPage"
DEFAULT_DELAY = 1.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Finance-Enhancer)"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


class VietstockFinanceEnhancer:
    """Thu thập báo cáo nghiên cứu và khuyến nghị giá mục tiêu từ finance.vietstock.vn."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb", delay: float = DEFAULT_DELAY) -> None:
        self.duckdb_path = duckdb_path
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.token: str | None = None
        self._init_schema()

    def _init_schema(self) -> None:
        """Khởi tạo bảng core.stock_research_reports trong DuckDB."""
        try:
            con = duckdb.connect(self.duckdb_path, read_only=False)
            con.execute("CREATE SCHEMA IF NOT EXISTS core;")
            con.execute("""
                CREATE TABLE IF NOT EXISTS core.stock_research_reports (
                    report_id VARCHAR,
                    symbol VARCHAR,
                    broker VARCHAR,
                    title VARCHAR NOT NULL,
                    recommendation VARCHAR,
                    target_price DOUBLE,
                    upside_pct DOUBLE,
                    report_date DATE,
                    report_url VARCHAR PRIMARY KEY,
                    pdf_url VARCHAR,
                    summary TEXT,
                    fetched_at TIMESTAMP NOT NULL
                );
            """)
            con.close()
        except Exception as e:
            logger.warning(f"Lỗi khởi tạo schema core.stock_research_reports: {e}")

    def get_existing_urls(self) -> set[str]:
        """Lấy danh sách các URL báo cáo đã tồn tại trong database để tránh cào lại."""
        try:
            con = duckdb.connect(self.duckdb_path, read_only=True)
            res = con.execute("SELECT report_url FROM core.stock_research_reports").fetchall()
            con.close()
            return {r[0] for r in res}
        except Exception:
            return set()

    def refresh_verification_token(self) -> str:
        """Lấy token xác thực __RequestVerificationToken từ trang chủ báo cáo."""
        logger.info("Đang lấy token chống giả mạo từ Vietstock Finance...")
        r = self.session.get(REPORT_PAGE_URL, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Tìm token trong form chống giả mạo
        form = soup.find("form", id="__CHART_AjaxAntiForgeryForm")
        token_input = form.find("input", attrs={"name": "__RequestVerificationToken"}) if form else None
        if not token_input:
            token_input = soup.find("input", attrs={"name": "__RequestVerificationToken"})

        if not token_input or not token_input.get("value"):
            raise RuntimeError("Không tìm thấy __RequestVerificationToken trên finance.vietstock.vn")

        self.token = token_input["value"]
        logger.info(f"Đã lấy token thành công: {self.token[:20]}...")
        return self.token

    @staticmethod
    def parse_report_items(html_fragment: str) -> list[dict[str, Any]]:
        """Trích xuất danh sách metadata báo cáo từ fragment HTML trả về qua AJAX."""
        soup = BeautifulSoup(html_fragment, "html.parser")
        items: list[dict[str, Any]] = []

        # Các link báo cáo có dạng /bao-cao-phan-tich/{id}/{slug}.htm
        links = soup.find_all("a", href=lambda h: h and "/bao-cao-phan-tich/" in h and h.endswith(".htm"))
        seen_urls = set()

        for link in links:
            url_suffix = link.get("href", "")
            full_url = urljoin(BASE_URL, url_suffix)
            if full_url in seen_urls:
                continue

            title = link.text.strip()
            if not title or len(title) < 5:
                continue
            seen_urls.add(full_url)

            # Trích xuất report_id từ URL
            id_match = re.search(r"/bao-cao-phan-tich/(\d+)/", url_suffix)
            report_id = id_match.group(1) if id_match else None

            # Trích xuất mã cổ phiếu nếu có dạng 'VCB: ...' hoặc 'HPG: ...'
            symbol_match = re.search(r"\b([A-Z0-9]{3})\b\s*:", title)
            symbol = symbol_match.group(1) if symbol_match else None

            # Trích xuất khuyến nghị
            rec_match = re.search(r"Khuyến nghị\s+(MUA|BÁN|THEO DÕI|KHẢ QUAN|TRUNG LẬP|NẮM GIỮ|TÍCH LŨY)", title, re.IGNORECASE)
            recommendation = rec_match.group(1).upper() if rec_match else None

            # Trích xuất giá mục tiêu
            tp_match = re.search(r"giá mục tiêu\s+([0-9\.,]+)", title, re.IGNORECASE)
            target_price = None
            if tp_match:
                try:
                    tp_str = tp_match.group(1).replace(".", "").replace(",", "")
                    target_price = float(tp_str)
                except ValueError:
                    target_price = None

            items.append({
                "report_id": report_id,
                "symbol": symbol,
                "title": title,
                "recommendation": recommendation,
                "target_price": target_price,
                "report_url": full_url,
            })
        return items

    def parse_report_detail(self, report_url: str) -> dict[str, Any]:
        """Tải trang chi tiết báo cáo để lấy thông tin CTCK, mô tả, ngày phát hành và file PDF."""
        try:
            time.sleep(self.delay)
            r = self.session.get(report_url, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            # 1. Trích xuất Schema.org JSON-LD
            description = ""
            broker = None
            date_published = None
            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    meta = json.loads(s.text.strip())
                    if "description" in meta:
                        description = meta["description"]
                    if "datePublished" in meta:
                        date_published = meta["datePublished"]
                except Exception:
                    continue

            # 2. Tìm file PDF đính kèm
            pdf_url = None
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" in href.lower() and "edocs" in href.lower():
                    pdf_url = href if href.startswith("http") else urljoin(BASE_URL, href)
                    break

            # 3. Trích xuất CTCK phát hành từ mô tả hoặc nội dung
            broker_match = re.search(r"(?:Chứng khoán|CTCK)\s+([A-Za-z0-9\s]+?)(?:\s+cập nhật|\s+khuyến nghị|\s+đánh giá|\s+cho rằng|\.|\,)", description)
            if broker_match:
                broker = broker_match.group(1).strip()

            # 4. Trích xuất upside nếu có
            upside_pct = None
            upside_match = re.search(r"upside\s*([+\-]?[0-9\.,]+)%", description, re.IGNORECASE)
            if upside_match:
                try:
                    upside_pct = float(upside_match.group(1).replace(",", "."))
                except ValueError:
                    pass

            # 5. Xác định ngày báo cáo
            report_date = None
            if date_published:
                try:
                    report_date = dt.datetime.fromisoformat(date_published.replace("Z", "+00:00")).date()
                except Exception:
                    pass
            if not report_date:
                # Tìm ngày dạng DD/MM/YYYY trong trang
                date_match = re.search(r"(?:Ngày phát hành|Ngày|Ngày tạo):\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", r.text)
                if date_match:
                    try:
                        report_date = dt.datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
                    except Exception:
                        pass
            if not report_date:
                report_date = dt.date.today()

            return {
                "broker": broker,
                "pdf_url": pdf_url,
                "summary": description[:2000] if description else None,
                "upside_pct": upside_pct,
                "report_date": report_date,
            }
        except Exception as e:
            logger.warning(f"Lỗi khi cào chi tiết báo cáo {report_url}: {e}")
            return {
                "broker": None,
                "pdf_url": None,
                "summary": None,
                "upside_pct": None,
                "report_date": dt.date.today(),
            }

    def fetch_report_page(self, page: int, page_size: int = 20) -> list[dict[str, Any]]:
        """Gửi request phân trang AJAX để lấy danh sách báo cáo trên trang chỉ định."""
        if not self.token:
            self.refresh_verification_token()

        ajax_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": REPORT_PAGE_URL,
        }
        payload = {
            "page": page,
            "pageSize": page_size,
            "reportTypeID": 58,  # Phân tích doanh nghiệp
            "__RequestVerificationToken": self.token,
        }

        resp = self.session.post(AJAX_REPORT_URL, data=payload, headers=ajax_headers, timeout=15)
        if resp.status_code == 400 or resp.status_code == 403:
            logger.info("Token hết hạn hoặc bị từ chối, làm mới token...")
            self.refresh_verification_token()
            payload["__RequestVerificationToken"] = self.token
            resp = self.session.post(AJAX_REPORT_URL, data=payload, headers=ajax_headers, timeout=15)

        resp.raise_for_status()
        return self.parse_report_items(resp.text)

    def save_reports_batch(self, reports: list[dict[str, Any]]) -> int:
        """Lưu danh sách báo cáo phân tích vào DuckDB với ON CONFLICT DO UPDATE và cơ chế Retry/Staging."""
        if not reports:
            return 0
        df = pd.DataFrame(reports)
        df["fetched_at"] = dt.datetime.now(dt.timezone.utc)

        max_retries = 5
        for attempt in range(max_retries):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=False)
                con.register("df_rep_batch", df)
                con.execute("""
                    INSERT INTO core.stock_research_reports (
                        report_id, symbol, broker, title, recommendation,
                        target_price, upside_pct, report_date, report_url,
                        pdf_url, summary, fetched_at
                    )
                    SELECT
                        report_id, symbol, broker, title, recommendation,
                        target_price, upside_pct, report_date, report_url,
                        pdf_url, summary, fetched_at
                    FROM df_rep_batch
                    ON CONFLICT (report_url) DO UPDATE SET
                        symbol = COALESCE(EXCLUDED.symbol, core.stock_research_reports.symbol),
                        broker = COALESCE(EXCLUDED.broker, core.stock_research_reports.broker),
                        recommendation = COALESCE(EXCLUDED.recommendation, core.stock_research_reports.recommendation),
                        target_price = COALESCE(EXCLUDED.target_price, core.stock_research_reports.target_price),
                        upside_pct = COALESCE(EXCLUDED.upside_pct, core.stock_research_reports.upside_pct),
                        pdf_url = COALESCE(EXCLUDED.pdf_url, core.stock_research_reports.pdf_url),
                        summary = COALESCE(EXCLUDED.summary, core.stock_research_reports.summary),
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.close()
                return len(df)
            except Exception as e:
                logger.warning(f"Thử lần {attempt + 1}/{max_retries} ghi DB bị khóa ({e}). Chờ 2s...")
                time.sleep(2.0)

        # Fallback lưu vào staging database nếu vesta.duckdb bị giữ khóa lâu
        staging_db = Path("d:/VESTA/db/staging_reports.duckdb")
        staging_db.parent.mkdir(parents=True, exist_ok=True)
        try:
            scon = duckdb.connect(str(staging_db), read_only=False)
            scon.execute("CREATE SCHEMA IF NOT EXISTS core;")
            scon.execute("""
                CREATE TABLE IF NOT EXISTS core.stock_research_reports (
                    report_id VARCHAR, symbol VARCHAR, broker VARCHAR,
                    title VARCHAR NOT NULL, recommendation VARCHAR,
                    target_price DOUBLE, upside_pct DOUBLE, report_date DATE,
                    report_url VARCHAR PRIMARY KEY, pdf_url VARCHAR,
                    summary TEXT, fetched_at TIMESTAMP NOT NULL
                );
            """)
            scon.register("df_rep_batch", df)
            scon.execute("""
                INSERT INTO core.stock_research_reports
                SELECT * FROM df_rep_batch
                ON CONFLICT (report_url) DO UPDATE SET fetched_at = EXCLUDED.fetched_at
            """)
            scon.close()
            logger.info(f"Đã lưu tạm {len(df)} bản ghi vào {staging_db}.")
        except Exception as se:
            logger.error(f"Lỗi khi lưu vào staging database: {se}")
        return len(df)

    def crawl(
        self,
        start_page: int = 1,
        max_pages: int | None = None,
        symbol_filter: str | None = None,
        dry_run: bool = False
    ) -> int:
        """Thực thi thu thập toàn bộ báo cáo phân tích và khuyến nghị CTCK."""
        existing_urls = self.get_existing_urls()
        logger.info(f"Đã nạp {len(existing_urls)} URL báo cáo đã có trong DB.")

        page = start_page
        total_ingested = 0

        while True:
            if max_pages and page > max_pages:
                logger.info(f"Đã đạt giới hạn tối đa {max_pages} trang.")
                break

            logger.info(f"==> Đang tải Báo cáo phân tích Vietstock: Trang {page}...")
            try:
                items = self.fetch_report_page(page=page)
            except Exception as e:
                logger.error(f"Lỗi khi tải trang {page}: {e}")
                break

            if not items:
                logger.info(f"Hết dữ liệu báo cáo tại trang {page}. Dừng.")
                break

            new_items = [it for it in items if it["report_url"] not in existing_urls]
            if symbol_filter:
                new_items = [it for it in new_items if it.get("symbol") == symbol_filter.upper()]

            logger.info(f"Trang {page}: Tìm thấy {len(items)} báo cáo ({len(new_items)} báo cáo mới).")

            batch_to_save = []
            for it in new_items:
                detail = self.parse_report_detail(it["report_url"])
                it.update(detail)
                batch_to_save.append(it)
                existing_urls.add(it["report_url"])
                logger.info(f"  [Report] {it.get('symbol', 'N/A')} - {it['title'][:55]}... | Target: {it.get('target_price')} | Broker: {it.get('broker')}")

            if batch_to_save and not dry_run:
                self.save_reports_batch(batch_to_save)
                total_ingested += len(batch_to_save)
                logger.info(f"Trang {page}: Đã lưu +{len(batch_to_save)} báo cáo vào DB.")
            elif dry_run:
                total_ingested += len(batch_to_save)

            page += 1
            time.sleep(self.delay)

        return total_ingested


def main() -> None:
    """Khởi chạy CLI cho Vietstock Finance Enhancer."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Vietstock Finance Enhancer (Research Reports & Target Prices)")
    parser.add_argument("--db-path", type=str, default="d:/VESTA/db/vesta_staging.duckdb", help="Đường dẫn file DuckDB (Mặc định: d:/VESTA/db/vesta_staging.duckdb)")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu cào (Mặc định: 1)")
    parser.add_argument("--max-pages", type=int, default=None, help="Số trang tối đa cần cào (Mặc định: Toàn bộ)")
    parser.add_argument("--symbol", type=str, default=None, help="Lọc theo mã cổ phiếu (ví dụ: VCB, HPG)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Thời gian chờ giữa các request (giây)")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không ghi vào DB")

    args = parser.parse_args()
    enhancer = VietstockFinanceEnhancer(duckdb_path=args.db_path, delay=args.delay)
    count = enhancer.crawl(start_page=args.start_page, max_pages=args.max_pages, symbol_filter=args.symbol, dry_run=args.dry_run)
    print(f"Tổng số báo cáo phân tích thu thập được: {count}")


if __name__ == "__main__":
    main()
