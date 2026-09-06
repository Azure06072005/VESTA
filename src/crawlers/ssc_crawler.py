"""Ủy ban Chứng khoán Nhà nước (ssc.gov.vn) Market Regulation & Enforcement Crawler.

Thu thập các quyết định xử phạt vi phạm hành chính, thanh tra - giám sát thị trường,
phê duyệt phát hành chứng khoán/tăng vốn, cấp phép CTCK và thông cáo điều hành của UBCKNN.
Lưu trữ vào `staging.macro_policy` và `core.macro_policy` với khóa chính `source_url`.
Tuân thủ nghiêm ngặt nguyên tắc idempotency, streaming persistence và zero look-ahead bias.
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
from urllib.parse import urljoin, parse_qs, urlparse

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://ssc.gov.vn"
DEFAULT_DELAY_SECONDS = 1.0

DEFAULT_HEADERS = {
    "Accept": "*/*",
}

# Danh mục điều hành, giám sát, thống kê thị trường & đào tạo của UBCKNN
SSC_CATEGORIES = {
    # 1. Nhóm Tin tức & Giám sát thị trường
    "thanhtra-gimst": {
        "name": "Thanh tra - Giám sát & Xử phạt vi phạm chứng khoán",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/thanhtra-gimst",
        "mucHienThi": "104",
        "doc_type": "Quyết định xử phạt vi phạm chứng khoán",
    },
    "thngbo-choiuhnh": {
        "name": "Thông báo & Chỉ đạo điều hành UBCKNN",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/thngbo-choiuhnh",
        "mucHienThi": "190",
        "doc_type": "Chỉ đạo điều hành UBCKNN",
    },
    "hotngphthnh": {
        "name": "Hoạt động phát hành chứng khoán, Tăng vốn & Chào bán",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/hotngphthnh",
        "mucHienThi": "",
        "doc_type": "Phê duyệt phát hành chứng khoán & Chào bán",
    },
    "hotngkinhdoanhck": {
        "name": "Hoạt động kinh doanh chứng khoán, CTCK & Quỹ đầu tư",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/hotngkinhdoanhck",
        "mucHienThi": "113",
        "doc_type": "Giám sát kinh doanh chứng khoán & CTCK",
    },
    "thngtincngb": {
        "name": "Thông tin công bố thị trường & Doanh nghiệp",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/thngtincngb",
        "mucHienThi": "102",
        "doc_type": "Thông tin công bố thị trường chứng khoán",
    },
    "hptcquct": {
        "name": "Hợp tác quốc tế & Tiến trình nâng hạng thị trường (FTSE/MSCI)",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/hptcquct",
        "mucHienThi": "111",
        "doc_type": "Hợp tác quốc tế & Nâng hạng thị trường",
    },
    "chinlcphttrinngnh": {
        "name": "Chiến lược phát triển thị trường chứng khoán đến 2030",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/chinlcphttrinngnh",
        "mucHienThi": "112",
        "doc_type": "Chiến lược phát triển ngành chứng khoán",
    },
    "dnhngmcututhumuasmcng": {
        "name": "Dự án, Hạng mục đầu tư & Mua sắm công nghệ",
        "path": "/webcenter/portal/ubck/pages_r/m/tintc-skin/dnhngmcututhumuasmcng",
        "mucHienThi": "114",
        "doc_type": "Đầu tư hạ tầng công nghệ chứng khoán",
    },
    # 2. Nhóm Thống kê & Dữ liệu vĩ mô thị trường
    "thngkthtrng": {
        "name": "Thống kê thị trường chứng khoán, Phái sinh VN30 & TPCP",
        "path": "/webcenter/portal/ubck/pages_r/m/thngtinthtrng/thngkthtrng",
        "mucHienThi": "",
        "doc_type": "Thống kê thị trường chứng khoán",
    },
    # 3. Nhóm Đào tạo & Nghiên cứu khoa học (SRTC)
    "thngtinoto": {
        "name": "Thông tin đào tạo & Sát hạch chứng chỉ hành nghề",
        "path": "/webcenter/portal/ubck/pages_r/m/oto/thngtinoto",
        "mucHienThi": "124",
        "doc_type": "Đào tạo nghiệp vụ & Chứng chỉ hành nghề",
    },
    "kinthcchngkhon": {
        "name": "Kiến thức thị trường chứng khoán",
        "path": "/webcenter/portal/ubck/pages_r/m/oto/kinthcchngkhon",
        "mucHienThi": "157",
        "doc_type": "Kiến thức thị trường chứng khoán",
    },
    "tikhoahc": {
        "name": "Đề tài nghiên cứu khoa học thị trường vốn",
        "path": "/webcenter/portal/ubck/pages_r/m/oto/tikhoahc",
        "mucHienThi": "153",
        "doc_type": "Nghiên cứu khoa học thị trường vốn",
    },
}

# Regex bóc tách số hiệu văn bản (Quyết định xử phạt, Thông tư, Nghị định, Công văn)
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:QĐ|TT|CT|NQ|TB|CV|NĐ)-(?:XPHC|UBCK|UBCKNN|BTC|CP|TTg))\b",
    re.IGNORECASE,
)

# Regex phân tích thời gian xuất bản: DD/MM/YYYY hoặc HH:MM:SS DD/MM/YYYY
DATETIME_PATTERN = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
    re.IGNORECASE,
)


def parse_ssc_datetime(text: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày giờ tiếng Việt thành UTC datetime."""
    match = DATETIME_PATTERN.search(text)
    if not match:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    hh = int(match.group(4)) if match.group(4) else 0
    mm = int(match.group(5)) if match.group(5) else 0

    try:
        local_dt = dt.datetime(year, month, day, hh, mm)
        # Giờ hành chính Việt Nam (UTC+7) -> UTC
        return local_dt - dt.timedelta(hours=7)
    except ValueError:
        return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def extract_doc_number(title: str, summary: str | None, body: str | None) -> str | None:
    """Trích xuất số hiệu quyết định xử phạt hoặc văn bản quy phạm pháp luật."""
    for text in (title, summary, body):
        if text:
            m = DOC_NUMBER_PATTERN.search(text)
            if m:
                return m.group(1).upper()
    return None


def extract_canonical_url(raw_href: str) -> str:
    """Tạo URL chuẩn hóa với tham số dDocName làm định danh duy nhất."""
    full_url = urljoin(BASE_URL, raw_href)
    parsed = urlparse(full_url)
    qs = parse_qs(parsed.query)
    doc_name = qs.get("dDocName", [None])[0]
    if doc_name:
        # Chuẩn hóa gọn lại theo dDocName
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?dDocName={doc_name}"
    return full_url


def parse_category_soup(html_text: str, category_slug: str) -> list[dict[str, str]]:
    """Trích xuất danh sách bài viết/quyết định từ trang danh mục SSC."""
    soup = BeautifulSoup(html_text, "html.parser")
    articles: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        title = a_tag.get_text(strip=True)

        if "dDocName=" not in href:
            continue

        canonical_url = extract_canonical_url(href)
        if canonical_url in seen_urls:
            continue

        if len(title) < 15:
            # Tìm thẻ tiêu đề hoặc đoạn văn lân cận nếu thẻ a không chứa text đầy đủ
            parent = a_tag.find_parent(["li", "tr", "div", "p"])
            if parent:
                parent_text = parent.get_text(strip=True)
                if len(parent_text) > len(title):
                    title = parent_text

        if len(title) < 15:
            continue

        seen_urls.add(canonical_url)
        articles.append({
            "url": canonical_url,
            "title": title,
            "category": category_slug,
        })

    return articles


def parse_article_soup(html_text: str, url: str, default_doc_type: str = "Chính sách chứng khoán") -> dict[str, Any] | None:
    """Bóc tách chi tiết quyết định xử phạt hoặc thông báo từ trang chi tiết SSC."""
    soup = BeautifulSoup(html_text, "html.parser")

    # 1. Tiêu đề
    h1 = soup.find("h1", class_="detail-title") or soup.find("h1") or soup.find(class_=lambda c: c and "detail-title" in c)
    if not h1:
        return None

    # Tách ngày tháng khỏi tiêu đề nếu nằm trong thẻ small
    time_tag = h1.find("small")
    date_str = time_tag.get_text(strip=True) if time_tag else ""
    if time_tag:
        time_tag.decompose()

    headline = h1.get_text(strip=True)
    if not headline or len(headline) < 10:
        return None

    # 2. Ngày ban hành
    if not date_str:
        clock_el = soup.find(class_=lambda c: c and "clock" in c.lower())
        if clock_el and clock_el.parent:
            date_str = clock_el.parent.get_text(strip=True)
        else:
            time_meta = soup.find(class_=lambda c: c and any(k in c.lower() for k in ["date", "time", "publish"]))
            date_str = time_meta.get_text(strip=True) if time_meta else ""

    published_at = parse_ssc_datetime(date_str)

    # 3. Nội dung văn bản
    content_container = soup.find(class_=lambda c: c and any(k in c for k in ["new-content", "cd-content", "content-detail", "detail-content"]))
    if not content_container:
        content_container = h1.parent if h1.parent else soup

    paragraphs = []
    for p in content_container.find_all(["p", "div"]):
        txt = p.get_text(strip=True)
        if len(txt) > 25 and not any(kw in txt.lower() for kw in ["in bài viết", "cỡ chữ", "quay lại", "thông tin liên hệ"]):
            paragraphs.append(txt)

    body = "\n\n".join(paragraphs) if paragraphs else headline
    if len(body) < 30:
        body = headline

    # 4. Tóm tắt
    summary = paragraphs[0][:400] if paragraphs else headline[:300]

    # 5. Phân loại & Số hiệu văn bản
    doc_number = extract_doc_number(headline, summary, body)
    doc_type = default_doc_type
    if "xử phạt" in headline.lower() or "vi phạm" in headline.lower():
        doc_type = "Quyết định xử phạt vi phạm chứng khoán"
    elif "chào bán" in headline.lower() or "phát hành" in headline.lower():
        doc_type = "Phê duyệt phát hành chứng khoán & Chào bán"
    elif "chỉ đạo" in headline.lower() or "thông báo" in headline.lower():
        doc_type = "Chỉ đạo điều hành UBCKNN"

    issuing_body = "Ủy ban Chứng khoán Nhà nước (UBCKNN)"
    if doc_number and "-CP" in doc_number:
        issuing_body = "Chính phủ"
    elif doc_number and "-BTC" in doc_number:
        issuing_body = "Bộ Tài chính"

    now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    return {
        "source": "ssc",
        "issuing_body": issuing_body,
        "doc_type": doc_type,
        "doc_number": doc_number,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline,
        "summary": summary,
        "body": body,
        "source_url": url,
        "fetched_at": now_utc,
    }


class SscCrawler:
    """Crawler thu thập chính sách điều hành và xử phạt vi phạm từ UBCKNN (ssc.gov.vn)."""

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
        """Lấy danh sách link bài viết từ trang chuyên mục UBCKNN."""
        cat_info = SSC_CATEGORIES.get(category_slug, {})
        muc_hien_thi = cat_info.get("mucHienThi", "")
        rel_path = cat_info.get("path", f"/webcenter/portal/ubck/pages_r/m/tintc-skin/{category_slug}")
        url = f"{BASE_URL}{rel_path}"

        params = {"selectedPage": page}
        if muc_hien_thi:
            params["docType"] = "TinBai"
            params["mucHienThi"] = muc_hien_thi

        try:
            resp = self.session.get(url, params=params, verify=False, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch SSC category {url}: HTTP {resp.status_code}")
                return []
            return parse_category_soup(resp.text, category_slug)
        except Exception as e:
            logger.error(f"Error fetching SSC category {url}: {e}")
            return []

    def fetch_article(self, url: str, default_doc_type: str = "Chính sách chứng khoán") -> dict[str, Any] | None:
        """Thu thập và phân tích trang bài viết/quyết định chi tiết."""
        try:
            resp = self.session.get(url, verify=False, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch article {url}: HTTP {resp.status_code}")
                return None
            return parse_article_soup(resp.text, url, default_doc_type=default_doc_type)
        except Exception as e:
            logger.error(f"Error fetching article {url}: {e}")
            return None

    def load_existing_urls(self) -> set[str]:
        """Tải danh sách URL đã có trong core.macro_policy để tránh cào lại."""
        try:
            conn = duckdb.connect(self.db_path, read_only=True)
            rows = conn.execute("SELECT source_url FROM core.macro_policy WHERE source = 'ssc'").fetchall()
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
        """Chạy quy trình cào dữ liệu toàn diện lịch sử chuẩn F004."""
        target_categories = categories or list(SSC_CATEGORIES.keys())
        all_records: list[dict[str, Any]] = []
        existing_urls = self.load_existing_urls()
        logger.info(f"Đã nạp {len(existing_urls)} URL UBCKNN hiện có trong database để khử trùng lặp.")

        for cat in target_categories:
            cat_name = SSC_CATEGORIES.get(cat, {}).get("name", cat)
            default_doc_type = SSC_CATEGORIES.get(cat, {}).get("doc_type", "Chính sách chứng khoán")
            logger.info(f"==> Đang thu thập danh mục UBCKNN: {cat} ({cat_name})")
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
            conn.register("df_ssc", df)

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
                FROM df_ssc
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
                FROM df_ssc
                ON CONFLICT (source_url) DO UPDATE SET
                    headline = EXCLUDED.headline,
                    summary = EXCLUDED.summary,
                    body = EXCLUDED.body,
                    doc_number = COALESCE(EXCLUDED.doc_number, core.macro_policy.doc_number),
                    fetched_at = EXCLUDED.fetched_at
            """)
            conn.close()
            logger.info(f"Đã nạp thành công {len(df)} bản ghi UBCKNN vào {self.db_path}.")
            return len(df)
        except Exception as e:
            logger.warning(f"Không thể ghi trực tiếp vào {self.db_path} ({e}). Đang lưu vào crawlers_staging.duckdb...")
            staging_db = Path("d:/VESTA/db/crawlers_staging.duckdb")
            try:
                sconn = duckdb.connect(str(staging_db), read_only=False)
                sconn.register("df_ssc", df)
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
                    FROM df_ssc
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
                    FROM df_ssc
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

            backup_json = Path("d:/VESTA/out/staging_ssc.json")
            backup_json.parent.mkdir(parents=True, exist_ok=True)
            df.to_json(backup_json, orient="records", force_ascii=False, indent=2, date_format="iso")
            logger.info(f"Đã sao lưu JSON tại {backup_json}.")
            return len(df)


def main() -> None:
    """Khởi chạy CLI cho SSC Crawler."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Crawler UBCKNN (ssc.gov.vn) Market Regulation & Enforcement")
    parser.add_argument("--categories", nargs="+", choices=list(SSC_CATEGORIES.keys()), help="Danh mục chỉ định")
    parser.add_argument("--max-pages", type=int, default=None, help="Số trang tối đa mỗi danh mục (Mặc định: None = toàn bộ)")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn bài viết mỗi danh mục")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Thời gian chờ giữa các request (giây)")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không lưu vào DB")

    args = parser.parse_args()
    crawler = SscCrawler(request_delay=args.delay)
    records = crawler.crawl(
        categories=args.categories,
        max_pages=args.max_pages,
        limit_per_category=args.limit,
        dry_run=args.dry_run,
    )
    print(f"Tổng số bản ghi UBCKNN thu thập được: {len(records)}")


if __name__ == "__main__":
    main()
