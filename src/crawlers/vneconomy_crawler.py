"""VnEconomy (vneconomy.vn) Financial, Macro & Industry Policy Crawler.

Thu thập các tin tức vĩ mô, chính sách tài chính - tiền tệ, ngân hàng, bất động sản,
đầu tư công và kinh tế số từ Tạp chí Kinh tế Việt Nam (VnEconomy).
Tuân thủ nghiêm ngặt RFC 9309 với `Crawl-delay: 1.0s` theo robots.txt của VnEconomy.
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

BASE_URL = "https://vneconomy.vn"
# Robots.txt của VnEconomy yêu cầu Crawl-delay: 1
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Danh mục chính sách vĩ mô & ngành kinh tế trọng yếu trên VnEconomy
VNECONOMY_CATEGORIES = {
    "tai-chinh.htm": "Tài chính - Ngân hàng, Tỷ giá & Thị trường vốn",
    "bat-dong-san.htm": "Bất động sản, Quy hoạch & Luật Đất đai",
    "dau-tu.htm": "Đầu tư, FDI, M&A & Dự án hạ tầng công",
    "kinh-te-so.htm": "Kinh tế số, Công nghệ & Chuyển đổi số",
    "tieu-dung.htm": "Tiêu & Dùng, Bán lẻ & Chuỗi cung ứng hàng hóa",
    "chung-khoan.htm": "Thị trường chứng khoán & Dòng tiền",
    "thi-truong.htm": "Thị trường hàng hóa & Giá cả",
    "kinh-te-the-gioi.htm": "Kinh tế thế giới & Thương mại toàn cầu",
    "nhip-cau-doanh-nghiep.htm": "Nhịp cầu Doanh nghiệp & Hoạt động sản xuất kinh doanh",
    "dan-sinh.htm": "Dân sinh, Lao động, Việc làm & An sinh xã hội",
    "dau-tu-ha-tang.htm": "Đầu tư hạ tầng giao thông, Đô thị & Logistics",
    "kinh-te-xanh.htm": "Kinh tế xanh, ESG, Năng lượng tái tạo & Net Zero",
}

# Regex bóc tách văn bản quy phạm pháp luật (Nghị quyết, Nghị định, Thông tư, Quyết định)
GOV_DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|TT|CT|CV)-(?:CP|TTg|NHNN|BTC|BCT|BXD|BTNMT|BKHĐT))\b",
    re.IGNORECASE,
)

# Regex phân tích thời gian xuất bản: HH:MM, DD/MM/YYYY hoặc DD/MM/YYYY
VNECONOMY_TIME_PATTERN = re.compile(
    r"(?:(\d{1,2}):(\d{2}),?\s*)?(\d{1,2})/(\d{1,2})/(\d{4})",
    re.IGNORECASE,
)


def parse_vneconomy_datetime(text: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày giờ VnEconomy thành UTC datetime."""
    match = VNECONOMY_TIME_PATTERN.search(text)
    if not match:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    hh = int(match.group(1)) if match.group(1) else 0
    mm = int(match.group(2)) if match.group(2) else 0
    day = int(match.group(3))
    month = int(match.group(4))
    year = int(match.group(5))

    try:
        # Giờ Việt Nam (ICT = UTC+7) chuyển đổi sang UTC
        local_dt = dt.datetime(year, month, day, hh, mm)
        return local_dt - dt.timedelta(hours=7)
    except ValueError:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def extract_doc_number(title: str, summary: str | None, body: str | None) -> str | None:
    """Tìm số hiệu văn bản quy phạm pháp luật nếu có trích dẫn trong bài."""
    for text in (title, summary, body):
        if text:
            m = GOV_DOC_NUMBER_PATTERN.search(text)
            if m:
                return m.group(1).upper()
    return None


def parse_category_soup(html_text: str, category_slug: str) -> list[dict[str, str]]:
    """Trích xuất danh sách link bài viết từ trang danh mục VnEconomy."""
    soup = BeautifulSoup(html_text, "html.parser")
    articles: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for a_tag in soup.select(
        ".story__title a, .featured-news a, .news-category-page a, article a, h3 a, h2 a, .story a"
    ):
        href = a_tag.get("href", "").strip()
        title = a_tag.get_text(strip=True)

        # Bài viết VnEconomy luôn có đuôi .htm, tiêu đề rõ ràng và slug chứa ít nhất 3 dấu gạch ngang
        if (
            not href.endswith(".htm")
            or href.count("-") < 3
            or len(title) < 18
            or any(
                nav in href
                for nav in [
                    "/tai-chinh.htm",
                    "/bat-dong-san.htm",
                    "/dau-tu.htm",
                    "/kinh-te-so.htm",
                    "/tieu-dung.htm",
                    "/chung-khoan.htm",
                    "/thi-truong.htm",
                    "/kinh-te-the-gioi.htm",
                    "/nhip-cau-doanh-nghiep.htm",
                    "/dan-sinh.htm",
                    "/dau-tu-ha-tang.htm",
                    "/kinh-te-xanh.htm",
                    "/video.htm",
                    "/index.htm",
                    "page=",
                ]
            )
        ):
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
    """Bóc tách chi tiết bài viết VnEconomy: tiêu đề, tóm tắt, nội dung, ngày giờ."""
    soup = BeautifulSoup(html_text, "html.parser")

    # 1. Tiêu đề (Bỏ qua logo h1)
    title = ""
    for sel in ["h1.article-header__title", "h1.detail__title", ".article-header h1", "h1:not(.logo)"]:
        t_tag = soup.select_one(sel)
        if t_tag and t_tag.get_text(strip=True):
            title = t_tag.get_text(strip=True)
            break
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

    if not title:
        return None

    # 2. Tóm tắt (Summary)
    summary = ""
    summary_tag = soup.select_one(".article-header__summary, .article-summary, [class*=summary]")
    if summary_tag and summary_tag.get_text(strip=True):
        summary = summary_tag.get_text(strip=True)
    if not summary:
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            summary = og_desc.get("content", "").strip()

    # 3. Ngày phát hành
    time_tag = soup.select_one('time, [data-field="distributionDate"], .article-meta__time, .detail__meta')
    time_text = time_tag.get_text(strip=True) if time_tag else ""
    published_at = parse_vneconomy_datetime(time_text)

    # 4. Nội dung chi tiết (Body)
    body_container = soup.select_one(".article-layout, .article-detail-section__main, .article-body")
    paragraphs: list[str] = []
    if body_container:
        for p in body_container.find_all("p"):
            p_text = p.get_text(strip=True)
            # Bỏ qua các đoạn quảng cáo / footer ngắn
            if len(p_text) > 10 and not any(kw in p_text.lower() for kw in ["chọn cỡ chữ", "nhỏ hơn lớn hơn"]):
                paragraphs.append(p_text)

    body = "\n\n".join(paragraphs) if paragraphs else summary

    # 5. Số hiệu văn bản & Cơ quan ban hành
    doc_num = extract_doc_number(title, summary, body)
    doc_type = "Báo cáo vĩ mô & Phân tích chính sách"
    issuing_body = "Tạp chí Kinh tế Việt Nam (VnEconomy)"

    if doc_num:
        doc_type = "Văn bản trích dẫn chính thức"
        if "NHNN" in doc_num:
            issuing_body = "Ngân hàng Nhà nước Việt Nam"
        elif "BTC" in doc_num:
            issuing_body = "Bộ Tài chính"
        elif "CP" in doc_num or "TTG" in doc_num:
            issuing_body = "Chính phủ / Thủ tướng Chính phủ"
        elif "BCT" in doc_num:
            issuing_body = "Bộ Công Thương"
        elif "BXD" in doc_num:
            issuing_body = "Bộ Xây dựng"

    now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    return {
        "source": "vneconomy",
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


class VnEconomyCrawler:
    """Crawler thu thập tin tức và chính sách kinh tế từ VnEconomy."""

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

    def fetch_category_page(self, category_slug: str, page: int = 1) -> list[dict[str, str]]:
        """Lấy danh sách bài viết từ trang phân loại."""
        url = f"{BASE_URL}/{category_slug}"
        params = {"page": page} if page > 1 else {}
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch category {url}: HTTP {resp.status_code}")
                return []
            return parse_category_soup(resp.text, category_slug)
        except Exception as e:
            logger.error(f"Error fetching category {url}: {e}")
            return []

    def fetch_article(self, url: str) -> dict[str, Any] | None:
        """Thu thập và phân tích trang bài viết chi tiết."""
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch article {url}: HTTP {resp.status_code}")
                return None
            return parse_article_soup(resp.text, url)
        except Exception as e:
            logger.error(f"Error fetching article {url}: {e}")
            return None

    def load_existing_urls(self) -> set[str]:
        """Tải danh sách URL đã có trong core.macro_policy để tránh cào lại bài cũ."""
        try:
            conn = duckdb.connect(self.db_path, read_only=True)
            rows = conn.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vneconomy'").fetchall()
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
        """Chạy pipeline thu thập theo cấu trúc chuẩn F004: phân trang liên tục đến hết lịch sử, lưu từng trang."""
        target_categories = categories or list(VNECONOMY_CATEGORIES.keys())
        all_records: list[dict[str, Any]] = []
        existing_urls = self.load_existing_urls()
        logger.info(f"Đã nạp {len(existing_urls)} URL VnEconomy hiện có trong database để khử trùng lặp.")

        for cat in target_categories:
            logger.info(f"==> Đang thu thập danh mục: {cat} ({VNECONOMY_CATEGORIES.get(cat, '')})")
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

                # Lọc ra các bài viết chưa từng cào (chuẩn F004)
                new_links = [item for item in links if item["url"] not in existing_urls]
                logger.info(f"[{cat}] Trang {page}: Phát hiện {len(links)} bài ({len(new_links)} bài mới chưa cào)")

                if not new_links:
                    logger.info(f"[{cat}] Trang {page}: Toàn bộ bài viết đã có trong DB. Chuyển sang trang tiếp...")
                    page += 1
                    time.sleep(self.request_delay)
                    continue

                page_records: list[dict[str, Any]] = []
                for item in new_links:
                    if limit_per_category and cat_count >= limit_per_category:
                        break

                    record = self.fetch_article(item["url"])
                    if record:
                        page_records.append(record)
                        all_records.append(record)
                        existing_urls.add(item["url"])
                        cat_count += 1
                        logger.info(f"[Ingested] {record['headline'][:60]}")
                    time.sleep(self.request_delay)

                # Lưu ngay dữ liệu của trang vừa cào vào DB (chuẩn F004 streaming persistence)
                if page_records and not dry_run:
                    self.save_to_database(page_records)
                    logger.info(f"[{cat}] Trang {page}: Đã lưu +{len(page_records)} bài mới vào DB.")

                if limit_per_category and cat_count >= limit_per_category:
                    logger.info(f"[{cat}] Đã đạt giới hạn {limit_per_category} bài cho danh mục.")
                    break

                page += 1

        return all_records

    def save_to_database(self, records: list[dict[str, Any]]) -> int:
        """Lưu danh sách bài viết vào DuckDB (staging và core) với đảm bảo khóa chính."""
        if not records:
            logger.info("Không có bản ghi nào để lưu.")
            return 0

        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["source_url"], keep="last")

        try:
            conn = duckdb.connect(self.db_path, read_only=False)
            conn.register("df_vneconomy", df)

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
                FROM df_vneconomy
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
                FROM df_vneconomy
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
            logger.warning(f"Không thể ghi trực tiếp vào {self.db_path} ({e}). Đang nạp vào crawlers_staging.duckdb...")
            staging_db = Path("d:/VESTA/db/crawlers_staging.duckdb")
            try:
                sconn = duckdb.connect(str(staging_db), read_only=False)
                sconn.register("df_vneconomy", df)
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
                    FROM df_vneconomy
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
                    FROM df_vneconomy
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

            backup_json = Path("d:/VESTA/out/staging_vneconomy.json")
            backup_json.parent.mkdir(parents=True, exist_ok=True)
            df.to_json(backup_json, orient="records", force_ascii=False, indent=2, date_format="iso")
            logger.info(f"Đã sao lưu JSON tại {backup_json}.")
            return len(df)


def main() -> None:
    """Điểm khởi chạy CLI cho VnEconomy Crawler."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Crawler VnEconomy Macro & Sector Policy")
    parser.add_argument("--categories", nargs="+", choices=list(VNECONOMY_CATEGORIES.keys()), help="Danh mục chỉ định (Mặc định: toàn bộ 12 chuyên mục)")
    parser.add_argument("--max-pages", type=int, default=None, help="Số trang tối đa mỗi danh mục (Mặc định: None = cào toàn bộ lịch sử)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn bài viết mỗi danh mục")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Thời gian chờ giữa các request (giây)")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không lưu vào DB")

    args = parser.parse_args()
    crawler = VnEconomyCrawler(request_delay=args.delay)
    records = crawler.crawl(
        categories=args.categories,
        max_pages=args.max_pages,
        limit_per_category=args.limit,
        dry_run=args.dry_run,
    )
    print(f"Tổng số bản ghi thu thập được: {len(records)}")


if __name__ == "__main__":
    main()
