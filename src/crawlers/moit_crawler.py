"""Bộ Công Thương (moit.gov.vn) Industry, Energy & Trade Policy Crawler.

Thu thập các thông báo điều hành giá xăng dầu, khung giá phát điện nhiệt điện khí,
quy hoạch điện lực, chính sách phòng vệ thương mại và công nghiệp từ Cổng TTĐT Bộ Công Thương.
Tác động trực tiếp lên các mã: POW, GAS, PLX, OIL, BSR, HPG, HSG, PC1, GEG.
Lưu trữ vào `staging.macro_policy` và `core.macro_policy` với khóa chính `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://moit.gov.vn"
DEFAULT_DELAY_SECONDS = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Danh mục tin tức, thông báo điều hành & chính sách năng lượng/công nghiệp
MOIT_CATEGORIES = {
    "thong-bao": "Thông báo điều hành giá xăng dầu & Quy chuẩn kỹ thuật",
    "phat-trien-nang-luong": "Phát triển Năng lượng, Biểu giá điện & Quy hoạch điện lực",
    "phat-trien-cong-nghiep/chinh-sach": "Chính sách Công nghiệp nền tảng, Thép & Luyện kim",
    "thi-truong-trong-nuoc": "Thị trường trong nước, Bình ổn giá & Cung ứng hàng hóa",
    "cong-thuong-cong-luan/thong-cao-bao-chi": "Thông cáo báo chí chính thức Bộ Công Thương",
    "thi-truong-nuoc-ngoai/hiep-dinh-evfta": "Hiệp định EVFTA & Xuất nhập khẩu",
}

# Regex bóc tách số hiệu văn bản điều hành
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:QĐ|TT|CT|TB|CV|NQ|NĐ)-(?:BCT|CP|TTg|BTC))\b",
    re.IGNORECASE,
)

# Regex phân tích thời gian xuất bản: Thứ 2, 27/07/2026|14:19 hoặc 27/07/2026
MOIT_DATETIME_PATTERN = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s*\|\s*(\d{1,2}):(\d{1,2}))?",
    re.IGNORECASE,
)


def parse_moit_datetime(text: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày giờ trên cổng Bộ Công Thương thành UTC datetime."""
    match = MOIT_DATETIME_PATTERN.search(text)
    if not match:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    hour = int(match.group(4)) if match.group(4) else 0
    minute = int(match.group(5)) if match.group(5) else 0

    try:
        local_dt = dt.datetime(year, month, day, hour, minute)
        return local_dt - dt.timedelta(hours=7)
    except ValueError:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def extract_doc_number(title: str, summary: str | None, body: str | None) -> str | None:
    """Tìm số hiệu văn bản Bộ Công Thương hoặc Chính phủ trong văn bản."""
    for text in (title, summary, body):
        if text:
            m = DOC_NUMBER_PATTERN.search(text)
            if m:
                return m.group(1).upper()
    return None


def parse_category_soup(html_text: str, category_slug: str) -> list[dict[str, str]]:
    """Trích xuất danh sách link bài viết từ trang chuyên mục Bộ Công Thương."""
    soup = BeautifulSoup(html_text, "html.parser")
    articles: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)

        if not href.endswith(".html") or len(title) < 18 or "/tin-tuc/" not in href:
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


def parse_article_soup(html_text: str, url: str) -> dict[str, Any] | None:
    """Bóc tách chi tiết bài viết chính sách Bộ Công Thương."""
    soup = BeautifulSoup(html_text, "html.parser")

    # 1. Tiêu đề
    og_title = soup.find("meta", property="og:title")
    h1 = soup.find("h1")
    title = (
        og_title["content"].strip()
        if og_title and og_title.get("content")
        else (h1.get_text(strip=True) if h1 else "")
    )
    if not title:
        return None

    # 2. Tóm tắt
    summary = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        summary = og_desc["content"].strip()

    # 3. Ngày phát hành
    date_el = soup.select_one(".post-date, [class*=post-date], .date, [class*=date]")
    date_text = date_el.get_text(strip=True) if date_el else ""
    published_at = parse_moit_datetime(date_text)

    # 4. Nội dung chi tiết (Body)
    body_container = soup.select_one(".content-detail, .news-content, .detail-content, .article-content")
    paragraphs: list[str] = []
    if body_container:
        for p in body_container.find_all("p"):
            pt = p.get_text(strip=True)
            if len(pt) > 15:
                paragraphs.append(pt)

    body = "\n\n".join(paragraphs) if paragraphs else summary

    # 5. Phân loại văn bản và cơ quan ban hành
    doc_num = extract_doc_number(title, summary, body)
    doc_type = "Thông báo điều hành & Tin tức chính sách"
    issuing_body = "Bộ Công Thương"

    if doc_num:
        if "/QĐ-" in doc_num:
            doc_type = "Quyết định phê duyệt"
        elif "/TT-" in doc_num:
            doc_type = "Thông tư quy định"
        elif "/TB-" in doc_num:
            doc_type = "Thông báo điều hành giá xăng dầu"
        elif "-CP" in doc_num or "-TTG" in doc_num:
            doc_type = "Nghị định / Nghị quyết Chính phủ"
            issuing_body = "Chính phủ / Thủ tướng Chính phủ"

    now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    return {
        "source": "moit",
        "issuing_body": issuing_body,
        "doc_type": doc_type,
        "doc_number": doc_num,
        "published_at": published_at,
        "available_at": published_at,
        "headline": title,
        "summary": summary if summary else None,
        "body": body if body else None,
        "source_url": url,
        "fetched_at": now_utc,
    }


class MoitCrawler:
    """Crawler thu thập chính sách năng lượng, giá xăng dầu & công nghiệp từ Bộ Công Thương."""

    def __init__(
        self,
        db_path: str = "d:/VESTA/db/vesta.duckdb",
        request_delay: float = DEFAULT_DELAY_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self.db_path = db_path
        self.request_delay = request_delay
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def load_existing_urls(self) -> set[str]:
        """Tải danh sách URL đã có trong core.macro_policy để khử trùng lặp."""
        try:
            conn = duckdb.connect(self.db_path, read_only=True)
            rows = conn.execute("SELECT source_url FROM core.macro_policy WHERE source = 'moit'").fetchall()
            conn.close()
            return {r[0] for r in rows if r[0]}
        except Exception:
            return set()

    def fetch_category_articles(self, category_slug: str) -> list[dict[str, str]]:
        """Thu thập danh sách bài viết thuộc chuyên mục."""
        url = f"{BASE_URL}/tin-tuc/{category_slug}"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Lỗi tải chuyên mục {url}: HTTP {resp.status_code}")
                return []
            return parse_category_soup(resp.text, category_slug)
        except Exception as e:
            logger.error(f"Lỗi khi tải chuyên mục {url}: {e}")
            return []

    def fetch_article(self, url: str) -> dict[str, Any] | None:
        """Thu thập nội dung bài viết chi tiết."""
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Lỗi tải bài viết {url}: HTTP {resp.status_code}")
                return None
            return parse_article_soup(resp.text, url)
        except Exception as e:
            logger.error(f"Lỗi khi tải bài viết {url}: {e}")
            return None

    def crawl(
        self,
        categories: list[str] | None = None,
        limit_per_category: int | None = None,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """Chạy quy trình thu thập toàn bộ chuyên mục Bộ Công Thương theo chuẩn F004."""
        target_categories = categories or list(MOIT_CATEGORIES.keys())
        all_records: list[dict[str, Any]] = []
        existing_urls = self.load_existing_urls()
        logger.info(f"Đã nạp {len(existing_urls)} URL MOIT hiện có để khử trùng lặp.")

        for cat in target_categories:
            logger.info(f"==> Đang thu thập chuyên mục MOIT: {cat} ({MOIT_CATEGORIES.get(cat, '')})")
            articles = self.fetch_category_articles(cat)
            new_articles = [a for a in articles if a["url"] not in existing_urls]
            logger.info(f"[{cat}] Tìm thấy {len(articles)} bài ({len(new_articles)} bài mới chưa cào)")

            if not new_articles:
                continue

            if limit_per_category:
                new_articles = new_articles[:limit_per_category]

            cat_records: list[dict[str, Any]] = []
            for item in new_articles:
                record = self.fetch_article(item["url"])
                if record:
                    cat_records.append(record)
                    all_records.append(record)
                    existing_urls.add(item["url"])
                    logger.info(f"[Ingested] {record['headline'][:60]}")
                time.sleep(self.request_delay)

            # Lưu từng chuyên mục ngay khi cào xong (chuẩn F004 streaming persistence)
            if cat_records and not dry_run:
                self.save_to_database(cat_records)
                logger.info(f"[{cat}] Đã lưu +{len(cat_records)} bản ghi vào DB.")

        return all_records

    def save_to_database(self, records: list[dict[str, Any]]) -> int:
        """Lưu danh sách bài viết vào DuckDB với kiểm soát khóa chính source_url."""
        if not records:
            return 0

        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["source_url"], keep="last")

        try:
            conn = duckdb.connect(self.db_path, read_only=False)
            conn.register("df_moit", df)

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
                FROM df_moit
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
                FROM df_moit
                ON CONFLICT (source_url) DO UPDATE SET
                    headline = EXCLUDED.headline,
                    summary = EXCLUDED.summary,
                    body = EXCLUDED.body,
                    doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
                    fetched_at = EXCLUDED.fetched_at
            """)
            conn.close()
            logger.info(f"Đã nạp thành công {len(df)} bản ghi vào {self.db_path}.")
            return len(df)
        except Exception as e:
            logger.warning(f"Lỗi khi ghi vào {self.db_path}: {e}. Lưu vào crawlers_staging.duckdb...")
            staging_db = Path("d:/VESTA/db/crawlers_staging.duckdb")
            try:
                sconn = duckdb.connect(str(staging_db), read_only=False)
                sconn.register("df_moit", df)
                sconn.execute("""
                    INSERT INTO core.macro_policy
                    SELECT * FROM df_moit
                    ON CONFLICT (source_url) DO UPDATE SET
                        headline = EXCLUDED.headline,
                        summary = EXCLUDED.summary,
                        body = EXCLUDED.body,
                        doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
                        fetched_at = EXCLUDED.fetched_at
                """)
                sconn.close()
            except Exception as se:
                logger.error(f"Lỗi lưu staging: {se}")
            return len(df)


def main() -> None:
    """Điểm khởi chạy CLI cho Bộ Công Thương Crawler."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Crawler Chính sách Năng lượng & Giá xăng dầu Bộ Công Thương")
    parser.add_argument("--categories", nargs="+", choices=list(MOIT_CATEGORIES.keys()), help="Chuyên mục chỉ định")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn bài viết mỗi chuyên mục")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ giữa các request")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không lưu")

    args = parser.parse_args()
    crawler = MoitCrawler(request_delay=args.delay)
    records = crawler.crawl(categories=args.categories, limit_per_category=args.limit, dry_run=args.dry_run)
    print(f"Tổng số bản ghi thu thập được: {len(records)}")


if __name__ == "__main__":
    main()
