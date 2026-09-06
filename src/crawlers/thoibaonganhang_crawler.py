"""Thời báo Ngân hàng (thoibaonganhang.vn) Monetary & Banking News Crawler.

Thu thập các tin tức thị trường tiền tệ, lãi suất, tỷ giá, hoạt động các TCTD,
chính sách điều hành của NHNN và thị trường chứng khoán từ Thời báo Ngân hàng
(Cơ quan ngôn luận của Ngân hàng Nhà nước Việt Nam).

Sử dụng cơ chế infinite scroll pagination qua endpoint `apicenter@/article_lm`.
Lưu trữ vào: `core.macro_policy` với khóa chính `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
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

BASE_URL = "https://thoibaonganhang.vn"
DEFAULT_DELAY = 0.8

TBNH_CATEGORIES = {
    "thi-truong-tien-te": {
        "name": "Thị trường tiền tệ & Lãi suất",
        "url": "https://thoibaonganhang.vn/ngan-hang/thi-truong-tien-te",
        "doc_type": "Thị trường tiền tệ & Lãi suất",
    },
    "hoat-dong-tctd": {
        "name": "Hoạt động các TCTD & Ngân hàng thương mại",
        "url": "https://thoibaonganhang.vn/ngan-hang/hoat-dong-cua-cac-tctd",
        "doc_type": "Hệ thống Ngân hàng & TCTD",
    },
    "chung-khoan": {
        "name": "Chứng khoán & Thị trường vốn",
        "url": "https://thoibaonganhang.vn/kinh-te/chung-khoan",
        "doc_type": "Thị trường chứng khoán",
    },
    "tai-chinh": {
        "name": "Tài chính & Thuế",
        "url": "https://thoibaonganhang.vn/kinh-te/tai-chinh",
        "doc_type": "Tài chính & Vĩ mô",
    },
    "doanh-nghiep": {
        "name": "Doanh nghiệp & Tín dụng",
        "url": "https://thoibaonganhang.vn/doanh-nghiep-doanh-nhan",
        "doc_type": "Doanh nghiệp & SXKD",
    },
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-TBNH)"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class ThoiBaoNganHangCrawler:
    """Crawler thu thập tin tức chính sách tiền tệ & ngân hàng từ Thời báo Ngân hàng."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb", delay: float = DEFAULT_DELAY) -> None:
        self.duckdb_path = duckdb_path
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_existing_urls(self) -> set[str]:
        """Lấy danh sách các URL Thời báo Ngân hàng đã tồn tại trong database."""
        try:
            con = duckdb.connect(self.duckdb_path, read_only=True)
            res = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'thoibaonganhang'").fetchall()
            con.close()
            return {r[0] for r in res}
        except Exception:
            return set()

    @staticmethod
    def parse_article_links(html: str) -> tuple[list[str], str | None]:
        """Trích xuất các liên kết bài viết và next_url từ fragment HTML."""
        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            # Link bài viết thường có dạng https://thoibaonganhang.vn/{slug}-{id}.html
            if re.search(r"-\d+\.html$", href):
                full_url = href if href.startswith("http") else urljoin(BASE_URL, href)
                if full_url not in seen and not any(x in full_url for x in ["/adsfw/", "facebook.com"]):
                    seen.add(full_url)
                    links.append(full_url)

        next_url = None
        next_input = soup.find(class_=re.compile(r"__MB_NEXT_URL", re.I))
        if next_input and next_input.get("value"):
            next_url = next_input["value"].strip()

        return links, next_url

    def fetch_article_detail(self, url: str, doc_type: str) -> dict[str, Any] | None:
        """Tải và trích xuất chi tiết bài viết Thời báo Ngân hàng."""
        try:
            time.sleep(self.delay)
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            h1 = soup.find("h1")
            headline = h1.text.strip() if h1 else ""
            if not headline and soup.title:
                headline = soup.title.text.strip().split(" - ")[0]

            if not headline or len(headline) < 5:
                return None

            sapo = soup.find(class_=re.compile(r"sapo|lead|summary|description", re.I))
            summary = sapo.text.strip() if sapo else ""
            if not summary:
                meta_desc = soup.find("meta", attrs={"name": "description"})
                summary = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else ""

            body_el = soup.find(class_=re.compile(r"content|detail-content|article-content", re.I))
            body_paragraphs = []
            if body_el:
                for p in body_el.find_all("p"):
                    text = p.text.strip()
                    if len(text) > 20 and not text.startswith("Nguồn:") and not text.startswith("Xem thêm:"):
                        body_paragraphs.append(text)
            body = "\n\n".join(body_paragraphs) if body_paragraphs else summary

            published_at = None
            time_el = soup.find(class_=re.compile(r"time|date|publish", re.I))
            if time_el:
                time_text = time_el.text.strip()
                m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)", time_text)
                if m:
                    try:
                        parsed = dt.datetime.strptime(m.group(1), "%d/%m/%Y %H:%M")
                        published_at = parsed - dt.timedelta(hours=7)
                    except ValueError:
                        try:
                            parsed = dt.datetime.strptime(m.group(1), "%d/%m/%Y")
                            published_at = parsed - dt.timedelta(hours=7)
                        except ValueError:
                            pass

            if not published_at:
                published_at = dt.datetime.now(dt.timezone.utc)

            return {
                "source": "thoibaonganhang",
                "issuing_body": "Thời báo Ngân hàng - Ngân hàng Nhà nước Việt Nam",
                "doc_type": doc_type,
                "doc_number": None,
                "published_at": published_at,
                "available_at": published_at,
                "headline": headline,
                "summary": summary[:2000] if summary else None,
                "body": body,
                "source_url": url,
                "fetched_at": dt.datetime.now(dt.timezone.utc),
            }
        except Exception as e:
            logger.warning(f"Lỗi khi tải chi tiết bài viết TBNH {url}: {e}")
            return None

    def save_batch(self, articles: list[dict[str, Any]]) -> int:
        """Lưu danh sách bài viết vào core.macro_policy kèm cơ chế Retry."""
        if not articles:
            return 0
        df = pd.DataFrame(articles)

        max_retries = 5
        for attempt in range(max_retries):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=False)
                con.register("df_tbnh_batch", df)
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
                    FROM df_tbnh_batch
                    ON CONFLICT (source_url) DO UPDATE SET
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        body = EXCLUDED.body,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.close()
                return len(df)
            except Exception as e:
                logger.warning(f"Thử {attempt+1}/{max_retries} nạp TBNH bị lock ({e}). Chờ 2s...")
                time.sleep(2.0)
        return len(df)

    def crawl(self, categories: list[str] | None = None, max_pages: int | None = None, dry_run: bool = False) -> int:
        """Thu thập tin tức từ các chuyên mục của Thời báo Ngân hàng."""
        cat_keys = categories or list(TBNH_CATEGORIES.keys())
        existing_urls = self.get_existing_urls()
        logger.info(f"Đã nạp {len(existing_urls)} URL TBNH đã có trong DB.")

        total_ingested = 0
        for cat_key in cat_keys:
            cat_info = TBNH_CATEGORIES.get(cat_key)
            if not cat_info:
                continue

            logger.info(f"==> Bắt đầu cào Thời báo Ngân hàng: {cat_key} ({cat_info['name']})")
            current_url: str | None = cat_info["url"]
            page = 1

            while current_url:
                if max_pages and page > max_pages:
                    break

                logger.info(f"[{cat_key}] Trang {page}: {current_url}")
                try:
                    r = self.session.get(current_url, timeout=15)
                    r.raise_for_status()
                except Exception as e:
                    logger.error(f"Lỗi tải trang {current_url}: {e}")
                    break

                links, next_url = self.parse_article_links(r.text)
                if not links:
                    logger.info("Không tìm thấy bài viết nào trên trang. Dừng.")
                    break

                new_links = [l for l in links if l not in existing_urls]
                logger.info(f"[{cat_key}] Trang {page}: Tìm thấy {len(links)} bài ({len(new_links)} bài mới).")

                batch = []
                for link in new_links:
                    article = self.fetch_article_detail(link, doc_type=cat_info["doc_type"])
                    if article:
                        batch.append(article)
                        existing_urls.add(link)
                        logger.info(f"  [Ingested] {article['headline'][:60]}...")

                if batch and not dry_run:
                    self.save_batch(batch)
                    total_ingested += len(batch)
                    logger.info(f"[{cat_key}] Trang {page}: Đã lưu +{len(batch)} bài vào DB.")
                elif dry_run:
                    total_ingested += len(batch)

                page += 1
                current_url = next_url
                time.sleep(self.delay)

        return total_ingested


def main() -> None:
    """Khởi chạy CLI cho Thời báo Ngân hàng Crawler."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Thời báo Ngân hàng Crawler (thoibaonganhang.vn)")
    parser.add_argument("--categories", nargs="+", choices=list(TBNH_CATEGORIES.keys()))
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    crawler = ThoiBaoNganHangCrawler(delay=args.delay)
    count = crawler.crawl(categories=args.categories, max_pages=args.max_pages, dry_run=args.dry_run)
    print(f"Tổng số bài viết Thời báo Ngân hàng thu thập được: {count}")


if __name__ == "__main__":
    main()
