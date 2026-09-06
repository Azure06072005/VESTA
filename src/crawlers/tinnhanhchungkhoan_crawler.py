"""Tin Nhanh Chung Khoan (tinnhanhchungkhoan.vn) Crawler.

Thu thập tin tức chuyên sâu về thị trường chứng khoán, doanh nghiệp niêm yết,
quyền cổ tức, đại hội đồng cổ đông và nhận định chuyên gia từ Tin Nhanh Chứng Khoán.
Lưu trữ vào `core.macro_policy` với khóa chính `source_url`.
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
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tinnhanhchungkhoan.vn"
SITEMAP_INDEX = "https://www.tinnhanhchungkhoan.vn/sitemap.xml"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


def parse_sitemap_urls(xml_content: str) -> list[dict[str, str]]:
    """Phân tích XML sitemap lấy danh sách URL bài viết và thời gian sửa đổi."""
    entries = []
    try:
        # Xóa namespace nếu có để dễ query
        clean_xml = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
        root = ET.fromstring(clean_xml)
        for url_node in root.findall(".//url"):
            loc = url_node.find("loc")
            lastmod = url_node.find("lastmod")
            if loc is not None and loc.text and "-post" in loc.text:
                entries.append({
                    "url": loc.text.strip(),
                    "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else ""
                })
    except Exception as e:
        logger.error(f"Lỗi phân tích XML sitemap Tin Nhanh Chứng Khoán: {e}")
    return entries


def parse_article_html(html: str, url: str) -> dict[str, Any] | None:
    """Bóc tách tiêu đề, ngày đăng, tóm tắt và nội dung toàn văn bài viết."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề bài viết
    meta_title = soup.find("meta", property="og:title")
    h1_tag = soup.find("h1")
    headline = meta_title.get("content").strip() if meta_title and meta_title.get("content") else (h1_tag.text.strip() if h1_tag else "")
    if not headline:
        return None

    # 2. Ngày xuất bản (article:published_time hoặc meta/time)
    pub_meta = soup.find("meta", property="article:published_time") or soup.find("meta", property="pubdate")
    published_at: dt.datetime | None = None
    if pub_meta and pub_meta.get("content"):
        try:
            val = pub_meta.get("content")
            # Chuẩn hóa timezone ISO 8601 (ví dụ +0700 -> +07:00)
            if re.search(r'\+\d{4}$', val):
                val = val[:-2] + ":" + val[-2:]
            published_at = dt.datetime.fromisoformat(val).astimezone(dt.timezone.utc).replace(tzinfo=None)
        except Exception:
            published_at = None

    if not published_at:
        time_tag = soup.find("time") or soup.select_one(".time, .datetime, .date")
        if time_tag:
            date_match = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', time_tag.text)
            if date_match:
                d, m, y = map(int, date_match.groups())
                published_at = dt.datetime(y, m, d)
            else:
                published_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        else:
            published_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    # 3. Tóm tắt (Sapo / description)
    meta_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    sapo_div = soup.select_one(".article__sapo, .sapo, .summary")
    summary = meta_desc.get("content").strip() if meta_desc and meta_desc.get("content") else (sapo_div.text.strip() if sapo_div else "")

    # 4. Nội dung chi tiết (Body)
    body_div = soup.select_one(".article__body, .cms-body, .detail-content, #content, .content")
    if body_div:
        # Xóa các khối quảng cáo, bài liên quan
        for unwanted in body_div.select(".banner, .ad, .relate-box, script, style, .box-embed"):
            unwanted.decompose()
        body = body_div.get_text(separator="\n", strip=True)
    else:
        body = summary

    if len(body) < 30:
        return None

    return {
        "source": "tinnhanhchungkhoan",
        "issuing_body": "Tin Nhanh Chứng Khoán",
        "doc_type": "news",
        "doc_number": None,
        "published_at": published_at,
        "available_at": published_at,  # Tuân thủ B4: không rò rỉ dữ liệu tương lai
        "headline": headline,
        "summary": summary[:2000] if summary else None,
        "body": body,
        "source_url": url,
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    }


class TinNhanhChungKhoanCrawler:
    """Trình thu thập dữ liệu tự động cho Tin Nhanh Chứng Khoán."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb", delay: float = 0.6):
        self.duckdb_path = duckdb_path
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_existing_urls(self) -> set[str]:
        """Tải danh sách URL đã lưu trong core.macro_policy để tránh cào lặp."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=True)
                rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'tinnhanhchungkhoan'").fetchall()
                con.close()
                return {r[0] for r in rows}
            except Exception as e:
                time.sleep(1.0)
        return set()

    def fetch_article(self, url: str) -> dict[str, Any] | None:
        """Tải và parse chi tiết một bài viết."""
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code != 200:
                return None
            return parse_article_html(resp.text, url)
        except Exception as e:
            logger.warning(f"Lỗi khi tải bài viết {url}: {e}")
            return None

    def save_batch(self, articles: list[dict[str, Any]]) -> int:
        """Lưu danh sách bài viết vào core.macro_policy kèm cơ chế chống lock DuckDB."""
        if not articles:
            return 0
        df = pd.DataFrame(articles)

        max_retries = 6
        for attempt in range(max_retries):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=False)
                con.register("df_tnck_batch", df)
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
                    FROM df_tnck_batch
                    ON CONFLICT (source_url) DO UPDATE SET
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        body = EXCLUDED.body,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.close()
                return len(df)
            except Exception as e:
                wait = (attempt + 1) * 1.5
                logger.warning(f"Lock DuckDB khi nạp Tin Nhanh CK (lần {attempt+1}/{max_retries}). Chờ {wait}s...")
                time.sleep(wait)
        return len(df)

    def crawl(self, months: list[str] | None = None, max_articles: int = 500, dry_run: bool = False) -> int:
        """Cào tin tức theo danh sách tháng (định dạng YYYY-M, ví dụ '2026-9', '2026-8')."""
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

        existing_urls = self.get_existing_urls()
        logger.info(f"Đã có {len(existing_urls)} URL Tin Nhanh Chứng Khoán trong DB.")

        target_months = months or ["2026-9", "2026-8", "2026-7"]
        total_saved = 0

        for m_str in target_months:
            sitemap_url = f"{BASE_URL}/sitemaps/news-{m_str}.xml"
            logger.info(f"==> Đang đọc sitemap tháng {m_str}: {sitemap_url}")
            try:
                r = self.session.get(sitemap_url, timeout=12)
                if r.status_code != 200:
                    logger.warning(f"Không tìm thấy sitemap {sitemap_url} (HTTP {r.status_code})")
                    continue
                entries = parse_sitemap_urls(r.text)
            except Exception as e:
                logger.error(f"Lỗi tải sitemap {sitemap_url}: {e}")
                continue

            new_entries = [e for e in entries if e["url"] not in existing_urls]
            logger.info(f"Tháng {m_str}: Tìm thấy {len(entries)} bài ({len(new_entries)} bài mới chưa có trong DB).")

            batch: list[dict[str, Any]] = []
            for item in new_entries:
                if total_saved >= max_articles:
                    logger.info(f"Đã đạt giới hạn tối đa {max_articles} bài trong phiên này.")
                    return total_saved

                art = self.fetch_article(item["url"])
                if art:
                    batch.append(art)
                    existing_urls.add(item["url"])
                    logger.info(f"  [Ingested] {art['headline'][:70]}...")

                if len(batch) >= 15:
                    if not dry_run:
                        self.save_batch(batch)
                    total_saved += len(batch)
                    batch = []

                time.sleep(self.delay)

            if batch:
                if not dry_run:
                    self.save_batch(batch)
                total_saved += len(batch)

        logger.info(f"==> Hoàn thành phiên cào Tin Nhanh CK: Đã lưu {total_saved} bài viết.")
        return total_saved


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Tin Nhanh Chung Khoan Ingestion Crawler")
    parser.add_argument("--months", nargs="+", help="Danh sách tháng cào (VD: 2026-9 2026-8)")
    parser.add_argument("--max-articles", type=int, default=300, help="Số bài tối đa trong đợt chạy")
    parser.add_argument("--delay", type=float, default=0.6, help="Độ trễ giữa các request")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không ghi vào DB")

    args = parser.parse_args()
    crawler = TinNhanhChungKhoanCrawler(delay=args.delay)
    crawler.crawl(months=args.months, max_articles=args.max_articles, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
