"""VASEP (vasep.com.vn) Crawler.

Thu thập dữ liệu xuất nhập khẩu thủy sản (tôm, cá tra, cá ngừ), chính sách thuế,
cảnh báo thẻ vàng IUU từ Hiệp hội Chế biến và Xuất khẩu Thủy sản Việt Nam (VASEP).
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

BASE_URL = "https://vasep.com.vn"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def parse_vasep_sitemap(xml_content: str) -> list[dict[str, str]]:
    """Trích xuất URL bài viết và thời gian sửa đổi từ sitemap VASEP."""
    entries = []
    try:
        clean_xml = re.sub(r'\sxmlns="[^"]+"', '', xml_content, count=1)
        root = ET.fromstring(clean_xml)
        for url_node in root.findall(".//url"):
            loc = url_node.find("loc")
            lastmod = url_node.find("lastmod")
            if loc is not None and loc.text and loc.text.endswith(".html"):
                entries.append({
                    "url": loc.text.strip(),
                    "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else ""
                })
    except Exception as e:
        logger.error(f"Lỗi phân tích sitemap VASEP: {e}")
    return entries


def parse_vasep_article(html: str, url: str) -> dict[str, Any] | None:
    """Bóc tách thông tin chi tiết bài viết VASEP."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề
    meta_title = soup.find("meta", property="og:title")
    h1_tag = soup.find("h1")
    headline = meta_title.get("content").strip() if meta_title and meta_title.get("content") else (h1_tag.text.strip() if h1_tag else "")
    if not headline or headline.lower() == "vasep":
        # Thử tìm thẻ tiêu đề bài viết con
        alt_h = soup.select_one(".title-detail, .entry-title")
        if alt_h:
            headline = alt_h.text.strip()

    if not headline:
        return None

    # 2. Ngày đăng
    pub_meta = soup.find("meta", property="article:published_time")
    published_at: dt.datetime | None = None
    if pub_meta and pub_meta.get("content"):
        try:
            val = pub_meta.get("content")
            if re.search(r'\+\d{4}$', val):
                val = val[:-2] + ":" + val[-2:]
            published_at = dt.datetime.fromisoformat(val).astimezone(dt.timezone.utc).replace(tzinfo=None)
        except Exception:
            published_at = None

    if not published_at:
        published_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    # 3. Tóm tắt
    meta_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    summary = meta_desc.get("content").strip() if meta_desc and meta_desc.get("content") else None

    # 4. Nội dung bài viết
    body_div = soup.select_one(".content-detail, .detail-content, .entry-content, #content, .content")
    if body_div:
        for unwanted in body_div.select(".banner, .ad, script, style"):
            unwanted.decompose()
        body = body_div.get_text(separator="\n", strip=True)
    else:
        body = summary or headline

    if len(body) < 30:
        return None

    return {
        "source": "vasep",
        "issuing_body": "Hiệp hội Chế biến và Xuất khẩu Thủy sản Việt Nam (VASEP)",
        "doc_type": "industry_report",
        "doc_number": None,
        "published_at": published_at,
        "available_at": published_at,  # Zero look-ahead bias
        "headline": headline,
        "summary": summary[:2000] if summary else None,
        "body": body,
        "source_url": url,
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
    }


class VasepCrawler:
    """Trình thu thập dữ liệu ngành thủy sản VASEP."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb", delay: float = 0.8):
        self.duckdb_path = duckdb_path
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get_existing_urls(self) -> set[str]:
        """Tải danh sách URL đã có trong core.macro_policy."""
        for _ in range(5):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=True)
                rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vasep'").fetchall()
                con.close()
                return {r[0] for r in rows}
            except Exception:
                time.sleep(1.0)
        return set()

    def save_batch(self, articles: list[dict[str, Any]]) -> int:
        """Lưu danh sách bài viết vào DuckDB có xử lý xung đột lock."""
        if not articles:
            return 0
        df = pd.DataFrame(articles)
        for attempt in range(6):
            try:
                con = duckdb.connect(self.duckdb_path, read_only=False)
                con.register("df_vasep_batch", df)
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
                    FROM df_vasep_batch
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

    def crawl(self, days_back: int = 15, max_articles: int = 150, dry_run: bool = False) -> int:
        """Quét sitemap VASEP theo ngày gần nhất."""
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

        existing_urls = self.get_existing_urls()
        logger.info(f"Đã có {len(existing_urls)} URL VASEP trong DB.")

        total_saved = 0
        today = dt.date.today()
        # VESTA runs in context of 2026-09-05
        base_date = dt.date(2026, 9, 5)

        for i in range(days_back):
            cur_date = base_date - dt.timedelta(days=i)
            sitemap_url = f"{BASE_URL}/sitemaps/newslist/{cur_date.year}-{cur_date.month}-{cur_date.day}.xml"
            try:
                r = self.session.get(sitemap_url, timeout=12)
                if r.status_code != 200:
                    continue
                entries = parse_vasep_sitemap(r.text)
            except Exception:
                continue

            new_entries = [e for e in entries if e["url"] not in existing_urls]
            logger.info(f"VASEP Ngày {cur_date}: Tìm thấy {len(entries)} bài ({len(new_entries)} bài mới).")

            batch: list[dict[str, Any]] = []
            for item in new_entries:
                if total_saved >= max_articles:
                    return total_saved

                try:
                    resp = self.session.get(item["url"], timeout=12)
                    if resp.status_code == 200:
                        art = parse_vasep_article(resp.text, item["url"])
                        if art:
                            batch.append(art)
                            existing_urls.add(item["url"])
                            logger.info(f"  [Ingested] {art['headline'][:70]}...")
                except Exception as e:
                    logger.warning(f"Lỗi tải bài VASEP {item['url']}: {e}")

                if len(batch) >= 10:
                    if not dry_run:
                        self.save_batch(batch)
                    total_saved += len(batch)
                    batch = []

                time.sleep(self.delay)

            if batch:
                if not dry_run:
                    self.save_batch(batch)
                total_saved += len(batch)

        return total_saved


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="VASEP Seafood Industry Crawler")
    parser.add_argument("--days", type=int, default=20, help="Số ngày quét lùi về trước")
    parser.add_argument("--max-articles", type=int, default=150, help="Số bài tối đa trong đợt chạy")
    parser.add_argument("--delay", type=float, default=0.8, help="Độ trễ request")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    crawler = VasepCrawler(delay=args.delay)
    n = crawler.crawl(days_back=args.days, max_articles=args.max_articles, dry_run=args.dry_run)
    print(f"Tổng số bài viết VASEP đã nạp: {n}")


if __name__ == "__main__":
    main()
