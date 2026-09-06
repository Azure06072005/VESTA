"""Báo Đầu tư (baodautu.vn) Financial, Equity & Investment News Crawler.

Thu thập các tin tức chứng khoán, ngân hàng, doanh nghiệp, đầu tư công và bất động sản
từ Báo Đầu tư (Cơ quan của Bộ Kế hoạch và Đầu tư).
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

BASE_URL = "https://baodautu.vn"
DEFAULT_DELAY = 0.8

BAODAUTU_CATEGORIES = {
    "chung-khoan": {
        "name": "Chứng khoán & Dòng tiền",
        "url": "https://baodautu.vn/chung-khoan-d4/",
        "doc_type": "Thị trường chứng khoán",
    },
    "ngan-hang": {
        "name": "Ngân hàng & Tiền tệ",
        "url": "https://baodautu.vn/ngan-hang-d5/",
        "doc_type": "Ngân hàng & Tiền tệ",
    },
    "doanh-nghiep": {
        "name": "Doanh nghiệp & SXKD",
        "url": "https://baodautu.vn/doanh-nghiep-d6/",
        "doc_type": "Doanh nghiệp niêm yết",
    },
    "dau-tu": {
        "name": "Đầu tư công & FDI",
        "url": "https://baodautu.vn/dau-tu-d7/",
        "doc_type": "Đầu tư & Vĩ mô",
    },
    "bat-dong-san": {
        "name": "Bất động sản & Quy hoạch",
        "url": "https://baodautu.vn/bat-dong-san-d8/",
        "doc_type": "Bất động sản",
    },
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-BaoDauTu)"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class BaoDauTuCrawler:
    """Crawler thu thập tin tức kinh tế, tài chính từ Báo Đầu tư."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb", delay: float = DEFAULT_DELAY) -> None:
        self.duckdb_path = duckdb_path
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_existing_urls(self) -> set[str]:
        """Lấy danh sách các URL Báo Đầu tư đã tồn tại trong database."""
        try:
            con = duckdb.connect(self.duckdb_path, read_only=True)
            res = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'baodautu'").fetchall()
            con.close()
            return {r[0] for r in res}
        except Exception:
            return set()

    @staticmethod
    def parse_article_links(html: str) -> list[str]:
        """Trích xuất các liên kết bài viết từ trang danh mục Báo Đầu tư."""
        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            # Link bài viết thường có dạng /slug-d{id}.html
            if re.search(r"-d\d+\.html$", href):
                full_url = urljoin(BASE_URL, href)
                if full_url not in seen and not any(x in full_url for x in ["video", "podcast", "photo"]):
                    seen.add(full_url)
                    links.append(full_url)
        return links

    def fetch_article_detail(self, url: str, doc_type: str) -> dict[str, Any] | None:
        """Tải và bóc tách chi tiết bài viết Báo Đầu tư."""
        try:
            time.sleep(self.delay)
            r = self.session.get(url, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            # Tiêu đề
            h1 = soup.find("h1")
            headline = h1.text.strip() if h1 else ""
            if not headline and soup.title:
                headline = soup.title.text.strip().split(" - ")[0]

            if not headline or len(headline) < 5:
                return None

            # Tóm tắt
            sapo = soup.find(class_=re.compile(r"sapo|summary|lead|description", re.I))
            summary = sapo.text.strip() if sapo else ""
            if not summary:
                meta_desc = soup.find("meta", attrs={"name": "description"})
                summary = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else ""

            # Nội dung
            body_el = soup.find(class_=re.compile(r"content|body|detail-content|post-content", re.I))
            body_paragraphs = []
            if body_el:
                for p in body_el.find_all("p"):
                    text = p.text.strip()
                    if len(text) > 20 and not text.startswith("Tag:") and not text.startswith("Xem thêm:"):
                        body_paragraphs.append(text)
            body = "\n\n".join(body_paragraphs) if body_paragraphs else summary

            # Ngày phát hành
            published_at = None
            time_el = soup.find(class_=re.compile(r"time|date|publish", re.I))
            if time_el:
                time_text = time_el.text.strip()
                # Tìm định dạng DD/MM/YYYY HH:MM hoặc YYYY-MM-DD
                m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)", time_text)
                if m:
                    try:
                        parsed = dt.datetime.strptime(m.group(1), "%d/%m/%Y %H:%M")
                        published_at = parsed - dt.timedelta(hours=7)  # sang UTC
                    except ValueError:
                        try:
                            parsed = dt.datetime.strptime(m.group(1), "%d/%m/%Y")
                            published_at = parsed - dt.timedelta(hours=7)
                        except ValueError:
                            pass

            if not published_at:
                # Tìm trong meta
                meta_time = soup.find("meta", property="article:published_time")
                if meta_time and meta_time.get("content"):
                    try:
                        published_at = dt.datetime.fromisoformat(meta_time["content"].replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)
                    except Exception:
                        pass

            if not published_at:
                published_at = dt.datetime.now(dt.timezone.utc)

            return {
                "source": "baodautu",
                "issuing_body": "Báo Đầu tư - Bộ Kế hoạch và Đầu tư",
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
            logger.warning(f"Lỗi khi cào bài viết Báo Đầu tư {url}: {e}")
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
                con.register("df_bdt_batch", df)
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
                    FROM df_bdt_batch
                    ON CONFLICT (source_url) DO UPDATE SET
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        body = EXCLUDED.body,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.close()
                return len(df)
            except Exception as e:
                logger.warning(f"Thử {attempt+1}/{max_retries} nạp Báo Đầu tư bị lock ({e}). Chờ 2s...")
                time.sleep(2.0)
        return len(df)

    def crawl(self, categories: list[str] | None = None, max_pages: int | None = None, dry_run: bool = False) -> int:
        """Thu thập tin tức từ các chuyên mục của Báo Đầu tư."""
        cat_keys = categories or list(BAODAUTU_CATEGORIES.keys())
        existing_urls = self.get_existing_urls()
        logger.info(f"Đã nạp {len(existing_urls)} URL Báo Đầu tư đã có trong DB.")

        total_ingested = 0
        for cat_key in cat_keys:
            cat_info = BAODAUTU_CATEGORIES.get(cat_key)
            if not cat_info:
                continue

            logger.info(f"==> Bắt đầu cào Báo Đầu tư: {cat_key} ({cat_info['name']})")
            page = 1
            while True:
                if max_pages and page > max_pages:
                    break

                page_url = cat_info["url"] if page == 1 else f"{cat_info['url']}p{page}"
                logger.info(f"[{cat_key}] Trang {page}: {page_url}")
                try:
                    r = self.session.get(page_url, timeout=15)
                    if r.status_code == 404:
                        logger.info(f"Hết trang tại {page}. Dừng chuyên mục.")
                        break
                    r.raise_for_status()
                except Exception as e:
                    logger.error(f"Lỗi tải trang {page_url}: {e}")
                    break

                links = self.parse_article_links(r.text)
                if not links:
                    logger.info("Không tìm thấy bài viết nào trên trang. Dừng chuyên mục.")
                    break

                new_links = [l for l in links if l not in existing_urls]
                logger.info(f"[{cat_key}] Trang {page}: Tìm thấy {len(links)} bài ({len(new_links)} bài mới).")

                if not new_links:
                    logger.info("Toàn bộ bài viết đã có trong DB. Dừng chuyên mục.")
                    break

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
                time.sleep(self.delay)

        return total_ingested


def main() -> None:
    """Khởi chạy CLI cho Báo Đầu tư Crawler."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Báo Đầu tư Crawler (baodautu.vn)")
    parser.add_argument("--categories", nargs="+", choices=list(BAODAUTU_CATEGORIES.keys()))
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    crawler = BaoDauTuCrawler(delay=args.delay)
    count = crawler.crawl(categories=args.categories, max_pages=args.max_pages, dry_run=args.dry_run)
    print(f"Tổng số bài viết Báo Đầu tư thu thập được: {count}")


if __name__ == "__main__":
    main()
