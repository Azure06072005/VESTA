"""Vietstock (vietstock.vn) Financial, Equity & Macro Market Crawler.

Thu thập các tin tức chứng khoán, doanh nghiệp niêm yết, phân tích dòng tiền,
chính sách vĩ mô, ngân hàng - tiền tệ, hàng hóa, phái sinh và trái phiếu từ Vietstock.
Sử dụng endpoint phân trang ChannelContentPage chính thức của Vietstock.
Lưu trữ vào `staging.macro_policy` và `core.macro_policy` với khóa chính `source_url`.
Tuân thủ nghiêm ngặt nguyên tắc idempotency, streaming persistence và zero look-ahead bias.
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
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://vietstock.vn"
AJAX_URL = "https://vietstock.vn/StartPage/ChannelContentPage"
DEFAULT_DELAY_SECONDS = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 10 Danh mục tài chính & chứng khoán trọng yếu trên Vietstock
VIETSTOCK_CATEGORIES = {
    "chung-khoan": {
        "name": "Thị trường chứng khoán & Dòng tiền",
        "channelID": 144,
        "doc_type": "Thị trường chứng khoán",
        "referer": "https://vietstock.vn/chung-khoan.htm",
    },
    "doanh-nghiep": {
        "name": "Doanh nghiệp niêm yết & Hoạt động SXKD",
        "channelID": 733,
        "doc_type": "Tin tức doanh nghiệp niêm yết",
        "referer": "https://vietstock.vn/doanh-nghiep.htm",
    },
    "tai-chinh": {
        "name": "Tài chính - Ngân hàng, Tiền tệ & Tỷ giá",
        "channelID": 734,
        "doc_type": "Tài chính - Ngân hàng",
        "referer": "https://vietstock.vn/tai-chinh.htm",
    },
    "bat-dong-san": {
        "name": "Bất động sản, Quy hoạch & Dự án",
        "channelID": 763,
        "doc_type": "Bất động sản & Quy hoạch",
        "referer": "https://vietstock.vn/bat-dong-san.htm",
    },
    "hang-hoa": {
        "name": "Thị trường hàng hóa, Năng lượng, Vàng & Thép",
        "channelID": 2,
        "doc_type": "Thị trường hàng hóa",
        "referer": "https://vietstock.vn/hang-hoa.htm",
    },
    "vi-mo": {
        "name": "Kinh tế vĩ mô, Lạm phát, GDP & Chính sách điều hành",
        "channelID": 761,
        "doc_type": "Kinh tế vĩ mô & Chính sách",
        "referer": "https://vietstock.vn/kinh-te/vi-mo.htm",
    },
    "kinh-te-dau-tu": {
        "name": "Kinh tế - Đầu tư công, FDI & Hạ tầng",
        "channelID": 768,
        "doc_type": "Kinh tế & Đầu tư công",
        "referer": "https://vietstock.vn/kinh-te/kinh-te-dau-tu.htm",
    },
    "chung-khoan-phai-sinh": {
        "name": "Chứng khoán phái sinh & Hợp đồng tương lai VN30",
        "channelID": 4186,
        "doc_type": "Chứng khoán phái sinh",
        "referer": "https://vietstock.vn/chung-khoan/chung-khoan-phai-sinh.htm",
    },
    "thi-truong-trai-phieu": {
        "name": "Thị trường trái phiếu Chính phủ & Doanh nghiệp",
        "channelID": 785,
        "doc_type": "Thị trường trái phiếu",
        "referer": "https://vietstock.vn/chung-khoan/thi-truong-trai-phieu.htm",
    },
    "tai-chinh-ca-nhan": {
        "name": "Tài chính cá nhân & Quản lý tài sản",
        "channelID": 4259,
        "doc_type": "Tài chính cá nhân",
        "referer": "https://vietstock.vn/tai-chinh-ca-nhan.htm",
    },
}

# Regex bóc tách số hiệu văn bản pháp luật trích dẫn trong bài nếu có
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|TT|CT|CV|TB)-(?:CP|TTg|NHNN|BTC|BCT|BXD|UBCK|UBCKNN))\b",
    re.IGNORECASE,
)

# Regex phân tích thời gian xuất bản định dạng Việt Nam nếu không có JSON-LD
VN_TIME_PATTERN = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?",
    re.IGNORECASE,
)


def parse_iso_or_vn_datetime(date_str: str) -> dt.datetime:
    """Chuyển đổi chuỗi ISO hoặc định dạng ngày tháng tiếng Việt sang UTC datetime."""
    if not date_str:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    # 1. Thử parse theo định dạng ISO 8601 từ JSON-LD (VD: 2026-09-04T19:32:00+07:00)
    try:
        iso_clean = date_str.replace("Z", "+00:00")
        parsed_dt = dt.datetime.fromisoformat(iso_clean)
        if parsed_dt.tzinfo is not None:
            return parsed_dt.astimezone(dt.timezone.utc).replace(tzinfo=None)
        # Nếu không có timezone thì giả định giờ Việt Nam (UTC+7)
        return parsed_dt - dt.timedelta(hours=7)
    except Exception:
        pass

    # 2. Thử parse theo regex tiếng Việt DD/MM/YYYY [HH:MM]
    m = VN_TIME_PATTERN.search(date_str)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4)) if m.group(4) else 0
        mm = int(m.group(5)) if m.group(5) else 0
        try:
            local_dt = dt.datetime(year, month, day, hh, mm)
            return local_dt - dt.timedelta(hours=7)
        except ValueError:
            pass

    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def extract_doc_number(title: str, summary: str | None, body: str | None) -> str | None:
    """Tìm số hiệu văn bản pháp lý hoặc quyết định được trích dẫn trong bài."""
    for text in (title, summary, body):
        if text:
            m = DOC_NUMBER_PATTERN.search(text)
            if m:
                return m.group(1).upper()
    return None


def parse_category_soup(html_text: str, category_slug: str) -> list[dict[str, str]]:
    """Trích xuất danh sách link bài viết từ HTML trả về của ChannelContentPage."""
    soup = BeautifulSoup(html_text, "html.parser")
    articles: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        title = a_tag.get_text(strip=True)

        # Bài viết của Vietstock có định dạng /{YYYY}/{MM}/{slug}-{channel}-{id}.htm
        if not (href.endswith(".htm") and ("-148" in href or "-147" in href or "-149" in href or re.search(r"-\d+-\d+\.htm", href))):
            continue

        if len(title) < 18:
            parent = a_tag.find_parent(["h4", "h3", "h2", "div", "li"])
            if parent:
                parent_title = parent.get_text(strip=True)
                if len(parent_title) > len(title):
                    title = parent_title

        if len(title) < 18:
            continue

        full_url = urljoin(BASE_URL, href)
        if full_url not in seen_urls:
            seen_urls.add(full_url)
            articles.append({
                "url": full_url,
                "title": title,
                "category": category_slug,
            })

    return articles


def parse_article_soup(html_text: str, url: str, default_doc_type: str = "Thị trường chứng khoán") -> dict[str, Any] | None:
    """Bóc tách chi tiết bài viết Vietstock từ JSON-LD và nội dung #vst_detail."""
    soup = BeautifulSoup(html_text, "html.parser")

    headline = ""
    summary = ""
    published_at: dt.datetime | None = None

    # 1. Trích xuất metadata chuẩn qua Schema.org JSON-LD nếu có
    for s_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s_tag.string or "")
            if isinstance(data, dict) and data.get("@type") == "NewsArticle":
                headline = data.get("headline", "").replace(" | Vietstock", "").strip()
                summary = data.get("description", "").strip()
                date_pub = data.get("datePublished") or data.get("dateCreated")
                if date_pub:
                    published_at = parse_iso_or_vn_datetime(date_pub)
                break
        except Exception:
            continue

    # 2. Fallback nếu JSON-LD thiếu
    if not headline:
        h1 = soup.find("h1", class_="article-title") or soup.find("h1")
        if h1:
            headline = h1.get_text(strip=True)

    if not headline:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            headline = og_title["content"].replace(" | Vietstock", "").strip()

    if not headline:
        return None

    if not summary:
        sapo = soup.find(class_=lambda c: c and any(k in c.lower() for k in ["sapo", "summary", "article-summary"]))
        if sapo:
            summary = sapo.get_text(strip=True)
        else:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                summary = og_desc["content"].strip()

    if not published_at:
        date_el = soup.find(class_=lambda c: c and any(k in c.lower() for k in ["date", "time", "published-date"]))
        date_str = date_el.get_text(strip=True) if date_el else ""
        published_at = parse_iso_or_vn_datetime(date_str)

    # 3. Nội dung bài viết từ #vst_detail
    content_div = soup.find("div", id="vst_detail") or soup.find("div", class_="article-content")
    paragraphs = []
    if content_div:
        for p in content_div.find_all(["p", "div"]):
            txt = p.get_text(strip=True)
            if len(txt) > 25 and not any(kw in txt.lower() for kw in ["vietstockfinance", "đọc tiếp", "bình luận", "in bài viết"]):
                paragraphs.append(txt)

    body = "\n\n".join(paragraphs) if paragraphs else summary
    if not body:
        body = headline

    # 4. Phân loại & Số hiệu văn bản
    doc_number = extract_doc_number(headline, summary, body)
    doc_type = default_doc_type
    if "xử phạt" in headline.lower() or "phạt" in headline.lower():
        doc_type = "Quyết định xử phạt vi phạm hành chính"
    elif "nghị quyết" in headline.lower() or (doc_number and "/NQ-" in doc_number):
        doc_type = "Nghị quyết"
    elif "nghị định" in headline.lower() or (doc_number and "/NĐ-" in doc_number):
        doc_type = "Nghị định"
    elif "thông tư" in headline.lower() or (doc_number and "/TT-" in doc_number):
        doc_type = "Thông tư"

    issuing_body = "Cổng thông tin Tài chính Vietstock"
    if doc_number:
        if "NHNN" in doc_number:
            issuing_body = "Ngân hàng Nhà nước Việt Nam"
        elif "BTC" in doc_number:
            issuing_body = "Bộ Tài chính"
        elif "UBCK" in doc_number:
            issuing_body = "Ủy ban Chứng khoán Nhà nước"
        elif "CP" in doc_number or "TTG" in doc_number:
            issuing_body = "Chính phủ / Thủ tướng Chính phủ"

    now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    return {
        "source": "vietstock",
        "issuing_body": issuing_body,
        "doc_type": doc_type,
        "doc_number": doc_number,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline,
        "summary": summary if summary else None,
        "body": body,
        "source_url": url,
        "fetched_at": now_utc,
    }


class VietstockCrawler:
    """Crawler thu thập tin tức chứng khoán và vĩ mô từ Vietstock (vietstock.vn)."""

    def __init__(
        self,
        db_path: str = "d:/VESTA/db/vesta.duckdb",
        request_delay: float = DEFAULT_DELAY_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self.db_path = db_path
        self.request_delay = request_delay
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_category_page(self, category_slug: str, page: int = 1) -> list[dict[str, str]]:
        """Gọi endpoint AJAX ChannelContentPage để lấy bài viết phân trang."""
        cat_info = VIETSTOCK_CATEGORIES.get(category_slug, {})
        channel_id = cat_info.get("channelID", 144)
        referer = cat_info.get("referer", f"{BASE_URL}/{category_slug}.htm")

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        }
        data = {
            "channelID": channel_id,
            "page": page,
        }

        try:
            resp = self.session.post(AJAX_URL, data=data, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch Vietstock category {category_slug} page {page}: HTTP {resp.status_code}")
                return []
            return parse_category_soup(resp.text, category_slug)
        except Exception as e:
            logger.error(f"Error fetching Vietstock category {category_slug}: {e}")
            return []

    def fetch_article(self, url: str, default_doc_type: str = "Thị trường chứng khoán") -> dict[str, Any] | None:
        """Thu thập và phân tích trang bài viết chi tiết."""
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch article {url}: HTTP {resp.status_code}")
                return None
            return parse_article_soup(resp.text, url, default_doc_type=default_doc_type)
        except Exception as e:
            logger.error(f"Error fetching article {url}: {e}")
            return None

    def load_existing_urls(self) -> set[str]:
        """Tải danh sách URL đã có trong core.macro_policy để tránh cào lại bài cũ."""
        try:
            conn = duckdb.connect(self.db_path, read_only=True)
            rows = conn.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vietstock'").fetchall()
            conn.close()
            return {r[0] for r in rows if r[0]}
        except Exception:
            return set()

    def crawl(
        self,
        categories: list[str] | None = None,
        max_pages: int | None = None,
        limit_per_category: int | None = None,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """Chạy pipeline cào toàn diện lịch sử chuẩn F004."""
        target_categories = categories or list(VIETSTOCK_CATEGORIES.keys())
        all_records: list[dict[str, Any]] = []
        existing_urls = self.load_existing_urls()
        logger.info(f"Đã nạp {len(existing_urls)} URL Vietstock hiện có trong database để khử trùng lặp.")

        for cat in target_categories:
            cat_name = VIETSTOCK_CATEGORIES.get(cat, {}).get("name", cat)
            default_doc_type = VIETSTOCK_CATEGORIES.get(cat, {}).get("doc_type", "Thị trường chứng khoán")
            logger.info(f"==> Đang thu thập danh mục Vietstock: {cat} ({cat_name})")
            cat_count = 0
            page = 1

            while True:
                if max_pages is not None and page > max_pages:
                    logger.info(f"[{cat}] Đã đạt giới hạn tối đa {max_pages} trang.")
                    break

                links = self.fetch_category_page(cat, page=page)
                if not links:
                    logger.info(f"[{cat}] Trang {page}: Không có bài viết mới hoặc đã chạm cuối lịch sử.")
                    break

                new_links = [item for item in links if item["url"] not in existing_urls]
                logger.info(f"[{cat}] Trang {page}: Tìm thấy {len(links)} bài ({len(new_links)} bài mới chưa cào)")

                if not new_links:
                    logger.info(f"[{cat}] Trang {page}: Toàn bộ bài viết đã có trong DB. Chuyển sang trang tiếp...")
                    page += 1
                    time.sleep(self.request_delay)
                    continue

                page_records: list[dict[str, Any]] = []
                for item in new_links:
                    if limit_per_category and cat_count >= limit_per_category:
                        break

                    record = self.fetch_article(item["url"], default_doc_type=default_doc_type)
                    if record:
                        page_records.append(record)
                        all_records.append(record)
                        existing_urls.add(item["url"])
                        cat_count += 1
                        logger.info(f"[Ingested] {record['headline'][:65]}")
                    time.sleep(self.request_delay)

                # Lưu streaming dữ liệu trang vào DuckDB (chuẩn F004)
                if page_records and not dry_run:
                    self.save_to_database(page_records)
                    logger.info(f"[{cat}] Trang {page}: Đã lưu +{len(page_records)} bài mới vào DB.")

                if limit_per_category and cat_count >= limit_per_category:
                    logger.info(f"[{cat}] Đã đạt giới hạn {limit_per_category} bài cho danh mục.")
                    break

                page += 1

        return all_records

    def save_to_database(self, records: list[dict[str, Any]]) -> int:
        """Lưu danh sách bài viết vào DuckDB với kiểm soát khóa chính và fallback staging."""
        if not records:
            return 0

        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["source_url"], keep="last")

        try:
            conn = duckdb.connect(self.db_path, read_only=False)
            conn.register("df_vietstock", df)

            conn.execute("""
                INSERT INTO staging.macro_policy (
                    source, issuing_body, doc_type, doc_number,
                    published_at, available_at, headline, summary,
                    body, source_url, fetched_at
                )
                SELECT
                    source, issuing_body, doc_type, doc_number,
                    published_at, available_at, headline, summary,
                    body, source_url, fetched_at
                FROM df_vietstock
            """)

            conn.execute("""
                INSERT INTO core.macro_policy (
                    source, issuing_body, doc_type, doc_number,
                    published_at, available_at, headline, summary,
                    body, source_url, fetched_at
                )
                SELECT
                    source, issuing_body, doc_type, doc_number,
                    published_at, available_at, headline, summary,
                    body, source_url, fetched_at
                FROM df_vietstock
                ON CONFLICT (source_url) DO UPDATE SET
                    headline = EXCLUDED.headline,
                    summary = EXCLUDED.summary,
                    body = EXCLUDED.body,
                    doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
                    fetched_at = EXCLUDED.fetched_at
            """)
            conn.close()
            logger.info(f"Đã nạp thành công {len(df)} bản ghi Vietstock vào {self.db_path}.")
            return len(df)
        except Exception as e:
            logger.warning(f"Không thể ghi trực tiếp vào {self.db_path} ({e}). Đang lưu vào crawlers_staging.duckdb...")
            staging_db = Path("d:/VESTA/db/crawlers_staging.duckdb")
            try:
                sconn = duckdb.connect(str(staging_db), read_only=False)
                sconn.register("df_vietstock", df)
                sconn.execute("""
                    INSERT INTO staging.macro_policy (
                        source, issuing_body, doc_type, doc_number,
                        published_at, available_at, headline, summary,
                        body, source_url, fetched_at
                    )
                    SELECT
                        source, issuing_body, doc_type, doc_number,
                        published_at, available_at, headline, summary,
                        body, source_url, fetched_at
                    FROM df_vietstock
                """)
                sconn.execute("""
                    INSERT INTO core.macro_policy (
                        source, issuing_body, doc_type, doc_number,
                        published_at, available_at, headline, summary,
                        body, source_url, fetched_at
                    )
                    SELECT
                        source, issuing_body, doc_type, doc_number,
                        published_at, available_at, headline, summary,
                        body, source_url, fetched_at
                    FROM df_vietstock
                    ON CONFLICT (source_url) DO UPDATE SET
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        body = EXCLUDED.body,
                        doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
                        fetched_at = EXCLUDED.fetched_at
                """)
                sconn.close()
                logger.info(f"Đã lưu thành công {len(df)} bản ghi vào {staging_db}.")
            except Exception as se:
                logger.error(f"Lỗi khi lưu vào staging db: {se}")

            backup_json = Path("d:/VESTA/out/staging_vietstock.json")
            backup_json.parent.mkdir(parents=True, exist_ok=True)
            df.to_json(backup_json, orient="records", force_ascii=False, indent=2, date_format="iso")
            logger.info(f"Đã sao lưu JSON tại {backup_json}.")
            return len(df)


def main() -> None:
    """Khởi chạy CLI cho Vietstock Crawler."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Crawler Vietstock (vietstock.vn) Financial & Market News")
    parser.add_argument("--categories", nargs="+", choices=list(VIETSTOCK_CATEGORIES.keys()), help="Danh mục chỉ định")
    parser.add_argument("--max-pages", type=int, default=None, help="Số trang tối đa mỗi danh mục (Mặc định: None = toàn bộ)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn bài viết mỗi danh mục")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Thời gian chờ giữa các request (giây)")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không lưu vào DB")

    args = parser.parse_args()
    crawler = VietstockCrawler(request_delay=args.delay)
    records = crawler.crawl(
        categories=args.categories,
        max_pages=args.max_pages,
        limit_per_category=args.limit,
        dry_run=args.dry_run,
    )
    print(f"Tổng số bản ghi Vietstock thu thập được: {len(records)}")


if __name__ == "__main__":
    main()
