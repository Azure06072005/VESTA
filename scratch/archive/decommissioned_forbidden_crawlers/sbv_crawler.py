"""Ngân hàng Nhà nước Việt Nam (sbv.gov.vn) Central Banking & Monetary Policy Crawler.

Thu thập các thông cáo báo chí, quyết định lãi suất điều hành, thông tư quy định,
chỉ thị và văn bản chỉ đạo điều hành của Ngân hàng Nhà nước Việt Nam.
Lưu trữ vào `staging.macro_policy` và `core.macro_policy` với khóa chính `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import urllib.robotparser

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://sbv.gov.vn"
ROBOTS_URL = "https://sbv.gov.vn/robots.txt"
DEFAULT_DELAY_SECONDS = 2.0
MAX_RETRIES = 3
COOLDOWN_ON_BLOCK_SECONDS = 60.0

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Regex trích xuất số văn bản điều hành của NHNN (VD: 02/2023/TT-NHNN, 1125/QĐ-NHNN, 01/CT-NHNN)
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:TT|QĐ|CT|NQ|TB|CV|NĐ)-(?:NHNN|CP|TTg))\b",
    re.IGNORECASE,
)

# Regex bóc tách thời gian dạng dd/mm/yyyy [hh:mm[:ss]]
DATETIME_PATTERN = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(?:\|\s*)?(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?"
)


def create_session() -> requests.Session:
    """Tạo HTTP Session tối ưu với đầy đủ browser headers."""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def clean_article_url(raw_url: str) -> str:
    """Lược bỏ query param thừa như redirect để tránh kích hoạt bộ lọc URI của WAF."""
    if not raw_url:
        return ""
    parts = urlsplit(raw_url)
    return urlunsplit((parts.scheme or "https", parts.netloc or "sbv.gov.vn", parts.path, "", ""))


def parse_vietnamese_datetime(date_str: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày giờ tiếng Việt thành datetime timezone-aware (UTC)."""
    if not date_str:
        return dt.datetime.now(dt.timezone.utc)

    match = DATETIME_PATTERN.search(date_str)
    if not match:
        return dt.datetime.now(dt.timezone.utc)

    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour = int(match.group(4)) if match.group(4) else 0
    minute = int(match.group(5)) if match.group(5) else 0
    second = int(match.group(6)) if match.group(6) else 0

    try:
        local_dt = dt.datetime(year, month, day, hour, minute, second)
        # Giờ hành chính Việt Nam UTC+7
        vn_tz = dt.timezone(dt.timedelta(hours=7))
        return local_dt.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def extract_sbv_doc_metadata(headline: str, body_text: str = "") -> tuple[str, str | None, str]:
    """Phân loại loại văn bản, số hiệu và cơ quan ban hành."""
    combined = f"{headline} {body_text[:1000]}"
    num_match = DOC_NUMBER_PATTERN.search(combined)
    doc_number = num_match.group(1).upper() if num_match else None

    # Phân loại văn bản
    if re.search(r"\b(?i:Thông\s+tư)\b", headline) or (doc_number and "/TT-" in doc_number):
        doc_type = "Thông tư"
    elif re.search(r"\b(?i:Quyết\s+định)\b", headline) or (doc_number and "/QĐ-" in doc_number):
        doc_type = "Quyết định"
    elif re.search(r"\b(?i:Chỉ\s+thị)\b", headline) or (doc_number and "/CT-" in doc_number):
        doc_type = "Chỉ thị"
    elif re.search(r"\b(?i:Lãi\s+suất|Tái\s+cấp\s+vốn|Điều\s+hành)\b", headline):
        doc_type = "Điều hành lãi suất"
    elif re.search(r"\b(?i:Tỷ\s+giá|Ngoại\s+hối|Dự\s+trữ)\b", headline):
        doc_type = "Chính sách tỷ giá & ngoại hối"
    elif re.search(r"\b(?i:Thông\s+cáo|Họp\s+báo)\b", headline):
        doc_type = "Thông cáo báo chí"
    elif re.search(r"\b(?i:Nghị\s+quyết)\b", headline) or (doc_number and "/NQ-" in doc_number):
        doc_type = "Nghị quyết"
    else:
        doc_type = "Chính sách tiền tệ"

    issuing_body = "Ngân hàng Nhà nước Việt Nam"
    if doc_number and "-CP" in doc_number:
        issuing_body = "Chính phủ"
    elif doc_number and "-TTG" in doc_number:
        issuing_body = "Thủ tướng Chính phủ"

    return doc_type, doc_number, issuing_body


def check_is_waf_rejected(html: str) -> bool:
    """Kiểm tra xem phản hồi có phải là thông báo chặn của F5 ASM hay không."""
    if not html or len(html) < 600:
        if "Request Rejected" in html or "Your support ID is:" in html:
            return True
    return False


def fetch_with_cooldown(
    session: requests.Session,
    url: str,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> str | None:
    """Thực hiện HTTP GET với cơ chế chờ giãn cách và tự động cooldown khi gặp WAF block."""
    for attempt in range(1, max_retries + 1):
        time.sleep(delay_seconds)
        try:
            resp = session.get(url, timeout=(10, 25))
            if resp.status_code == 404:
                logger.warning(f"URL 404 Not Found: {url}")
                return None

            html = resp.text
            if check_is_waf_rejected(html):
                logger.warning(
                    f"[Attempt {attempt}/{max_retries}] Gặp phản hồi 'Request Rejected' từ SBV WAF. "
                    f"Đang tạm dừng {COOLDOWN_ON_BLOCK_SECONDS}s để bảo đảm an toàn..."
                )
                time.sleep(COOLDOWN_ON_BLOCK_SECONDS)
                continue

            resp.raise_for_status()
            return html
        except Exception as e:
            logger.warning(f"[Attempt {attempt}/{max_retries}] Lỗi khi tải {url}: {e}")
            if attempt < max_retries:
                time.sleep(5.0)

    return None


def parse_sbv_news_listing(html: str) -> list[dict[str, Any]]:
    """Bóc tách danh sách bài viết từ trang phân trang Liferay của SBV."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls = set()

    # Tìm các thẻ link tiêu đề có class title-news-link
    links = soup.find_all("a", class_="title-news-link")
    for a in links:
        raw_title = a.get_text(strip=True)
        raw_href = a.get("href", "").strip()

        if not raw_title or len(raw_title) < 10 or not raw_href:
            continue

        clean_url = clean_article_url(raw_href)
        if clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)

        # Tìm chuỗi ngày tháng ở khối cha gần nhất
        parent = a.find_parent("div")
        date_str = None
        if parent:
            date_el = parent.find(class_=lambda c: c and any(k in c.lower() for k in ["date-about", "date", "publish"]))
            if date_el:
                date_str = date_el.get_text(strip=True)

        full_fetch_url = raw_href if raw_href.startswith("http") else f"{BASE_URL}{raw_href}"
        articles.append({
            "title": raw_title,
            "url": clean_url,
            "fetch_url": full_fetch_url,
            "date_str": date_str,
        })

    return articles


def parse_sbv_article_record(
    html: str,
    url: str,
    fallback_title: str = "",
    fallback_date_str: str | None = None,
) -> dict[str, Any] | None:
    """Phân tích chi tiết bài viết chính sách tiền tệ NHNN."""
    if check_is_waf_rejected(html):
        return None

    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề
    h1 = soup.find("h1")
    title_news = soup.find(class_=lambda c: c and any(k in c.lower() for k in ["title-news", "header-title"]))
    og_title = soup.find("meta", property="og:title")
    headline = (
        h1.get_text(strip=True)
        if h1
        else (
            title_news.get_text(strip=True)
            if title_news
            else (og_title.get("content") if og_title else fallback_title)
        )
    ).strip()

    if not headline:
        return None

    # 2. Thời gian ban hành
    date_el = soup.find(class_=lambda c: c and any(k in c.lower() for k in ["date-about", "publish-date", "metadata-publish-date"]))
    date_str = date_el.get_text(strip=True) if date_el else fallback_date_str
    published_at = parse_vietnamese_datetime(date_str) if date_str else dt.datetime.now(dt.timezone.utc)

    # 3. Nội dung văn bản
    content_div = soup.find("div", class_=lambda c: c and any(k in c.lower() for k in ["journal-content-article", "content-body", "article-content"]))
    if not content_div:
        content_div = soup.find("div", class_="portlet-content")

    body = content_div.get_text(separator="\n", strip=True) if content_div else None
    if not body or len(body) < 80:
        return None

    # 4. Trích yếu / Tóm tắt
    sapo = soup.find("div", class_=lambda c: c and "sapo" in c.lower())
    summary = sapo.get_text(strip=True) if sapo else body[:300]

    # 5. Metadata phân loại
    doc_type, doc_number, issuing_body = extract_sbv_doc_metadata(headline, body)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "sbv",
        "issuing_body": issuing_body,
        "doc_type": doc_type,
        "doc_number": doc_number,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline,
        "summary": summary,
        "body": body,
        "source_url": url,
        "fetched_at": now,
    }


def write_sbv_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu chính sách NHNN vào staging và core với cơ chế idempotent."""
    if df.empty:
        return 0

    required_cols = [
        "source",
        "issuing_body",
        "doc_type",
        "doc_number",
        "published_at",
        "available_at",
        "headline",
        "summary",
        "body",
        "source_url",
        "fetched_at",
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Thiếu cột bắt buộc '{col}' trong DataFrame")

    con.register("df_sbv_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_sbv_staging")
    con.unregister("df_sbv_staging")

    con.register("df_sbv_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_sbv_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_sbv_core")

    return n_written


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL đã có trong core.macro_policy để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'sbv'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def build_page_url(page: int, delta: int = 12) -> str:
    """Tạo URL phân trang theo chuẩn Liferay Asset Publisher của SBV."""
    if page <= 1:
        return f"{BASE_URL}/vi/tin-tuc-su-kien"
    return (
        f"{BASE_URL}/vi/tin-tuc-su-kien?"
        f"p_p_id=com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_jaxi"
        f"&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        f"&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_jaxi_redirect=%2Fvi%2Ftin-tuc-su-kien"
        f"&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_jaxi_delta={delta}"
        f"&p_r_p_resetCur=false"
        f"&_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_jaxi_cur={page}"
    )


def run_sbv_crawler(
    start_page: int = 1,
    max_pages: int = 5,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy quy trình cào dữ liệu điều hành chính sách tiền tệ của NHNN."""
    session = create_session()

    target_db = db_path
    try:
        test_con = db.connect(db_path, read_only=False)
        test_con.close()
    except Exception as e:
        logger.warning(f"Không thể mở {db_path} ({e}). Sử dụng db/crawlers_staging.duckdb...")
        target_db = "db/crawlers_staging.duckdb"

    # Tải danh sách URLs hiện có và đóng kết nối ngay để tránh giữ khóa
    read_con = duckdb.connect(target_db, read_only=True)
    existing_urls = load_existing_urls(read_con)
    read_con.close()

    total_discovered = 0
    total_written = 0

    logger.info(f"=== Bắt đầu cào chính sách tiền tệ NHNN (sbv.gov.vn): Trang {start_page}..{max_pages} ===")

    for page in range(start_page, max_pages + 1):
        page_url = build_page_url(page)
        logger.info(f"[SBV] Đang tải danh sách trang {page}/{max_pages}: {page_url}")

        html = fetch_with_cooldown(session, page_url, delay_seconds=delay_seconds)
        if not html:
            logger.warning(f"[SBV] Không thể tải trang {page}. Kết thúc crawl.")
            break

        articles = parse_sbv_news_listing(html)
        if not articles:
            logger.info(f"[SBV] Trang {page} không có bài viết mới hoặc đã chạm cuối danh mục.")
            break

        total_discovered += len(articles)
        new_articles = [a for a in articles if a["url"] not in existing_urls]

        if not new_articles:
            logger.info(f"[SBV] Trang {page}: Toàn bộ {len(articles)} bài đã có trong DB. Tiếp tục trang sau.")
            continue

        records = []
        for art in new_articles:
            canonical_url = art["url"]
            fetch_url = art.get("fetch_url", canonical_url)
            art_html = fetch_with_cooldown(session, fetch_url, delay_seconds=delay_seconds)
            if not art_html:
                continue

            rec = parse_sbv_article_record(
                art_html,
                canonical_url,
                fallback_title=art["title"],
                fallback_date_str=art["date_str"],
            )
            if rec:
                records.append(rec)
                existing_urls.add(canonical_url)

        if records:
            df_page = pd.DataFrame(records)
            write_con = duckdb.connect(target_db, read_only=False)
            n_written = write_sbv_macro_policy(write_con, df_page)
            write_con.close()
            total_written += n_written
            logger.info(
                f"[SBV] Trang {page:2d}: {len(records)} bài bóc tách thành công, +{n_written} bản ghi lưu vào core.macro_policy"
            )

    logger.info(
        f"=== Hoàn tất cào NHNN (sbv.gov.vn): Tổng tìm thấy {total_discovered}, đã lưu mới {total_written} ==="
    )
    return {
        "total_discovered": total_discovered,
        "total_written": total_written,
        "start_page": start_page,
        "max_pages": max_pages,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Bộ cào dữ liệu điều hành chính sách tiền tệ NHNN (sbv.gov.vn)")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu (mặc định: 1)")
    parser.add_argument("--max-pages", type=int, default=5, help="Số trang tối đa cần cào (mặc định: 5)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ giữa các request (giây)")
    parser.add_argument("--db", default="db/vesta.duckdb", help="Đường dẫn file DuckDB")
    args = parser.parse_args()

    summary = run_sbv_crawler(
        start_page=args.start_page,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        db_path=args.db,
    )
    print("\n=== Tổng kết cào dữ liệu NHNN Việt Nam ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
