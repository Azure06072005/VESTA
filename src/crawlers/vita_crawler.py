"""Hiệp hội Du lịch Việt Nam (vita.vn) Tourism, Hospitality & Aviation Policy Crawler.

Thu thập các thông tin chính sách thị thực (visa), thống kê lượng khách quốc tế,
định hướng phục hồi và kích cầu du lịch từ Hiệp hội Du lịch Việt Nam (VITA).
Tác động trực tiếp lên các mã cổ phiếu ngành hàng không, vận tải hành khách và dịch vụ du lịch (HVN, VJC, SKG, DAH, VTD).
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

BASE_URL = "https://vita.vn"
DEFAULT_DELAY_SECONDS = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Các chuyên mục chính sách, thống kê và văn bản của VITA
VITA_CATEGORIES = {
    "news": "Tin tức & Sự kiện Du lịch",
    "industry": "Thông tin Ngành & Thống kê du khách",
    "state-management": "Quản lý nhà nước về du lịch",
    "archives": "Văn bản của Hiệp hội VITA",
}

# Regex bóc tách ngày đăng dạng: dd/mm/yyyy hoặc dd-mm-yyyy
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_vita_date(text: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày đăng tiếng Việt thành UTC datetime."""
    match = DATE_PATTERN.search(text)
    if not match:
        return dt.datetime.now(dt.timezone.utc)

    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        local_dt = dt.datetime(year, month, day, 8, 0, 0)
        vn_tz = dt.timezone(dt.timedelta(hours=7))
        return local_dt.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def extract_vita_doc_metadata(headline: str, body_text: str = "") -> tuple[str, str | None, str]:
    """Trích xuất loại văn bản, số hiệu (nếu có) và cơ quan ban hành."""
    combined = f"{headline} {body_text[:1000]}"

    # Tìm số hiệu văn bản (nếu là công văn hoặc nghị quyết)
    doc_match = re.search(r"\b(\d+(?:/[0-9]{4})?/(?:CV|NQ|QĐ|TT|KH)-(?:VITA|HHDLVN|BVHTTDL|TCDL))\b", combined, re.IGNORECASE)
    doc_number = doc_match.group(1).upper() if doc_match else None

    # Phân loại tài liệu
    if re.search(r"\b(?i:visa|thị\s+thực|xuất\s+nhập\s+cảnh|miễn\s+thị\s+thực)\b", combined):
        doc_type = "Chính sách visa & xuất nhập cảnh"
    elif re.search(r"\b(?i:lượng\s+khách|khách\s+quốc\s+tế|hàng\s+không|chuyến\s+bay|HVN|VJC|SKG)\b", combined):
        doc_type = "Thống kê lượng khách du lịch & hàng không"
    elif re.search(r"\b(?i:khách\s+sạn|lưu\s+trú|nghỉ\s+dưỡng|resort|DAH)\b", combined):
        doc_type = "Chính sách phát triển lưu trú & khách sạn"
    elif re.search(r"\b(?i:văn\s+bản|công\s+văn|quyết\s+định|nghị\s+quyết)\b", headline):
        doc_type = "Văn bản điều hành du lịch"
    else:
        doc_type = "Hoạt động xúc tiến & thị trường du lịch"

    issuing_body = "Hiệp hội Du lịch Việt Nam (VITA)"

    return doc_type, doc_number, issuing_body


def build_vita_page_url(cat_slug: str, page: int) -> str:
    """Tạo URL phân trang theo cấu trúc của website vita.vn."""
    if cat_slug == "news":
        if page == 1:
            return f"{BASE_URL}/vi/news.html"
        offset = (page - 1) * 9
        return f"{BASE_URL}/index.php?com=news&fun=main&page={offset}"
    elif cat_slug == "industry":
        return f"{BASE_URL}/vi/industry.html"
    elif cat_slug == "state-management":
        return f"{BASE_URL}/vi/state-management.html"
    elif cat_slug == "archives":
        return f"{BASE_URL}/vi/archives.html"
    return f"{BASE_URL}/vi/{cat_slug}.html"


def parse_vita_listing(html: str) -> list[dict[str, str]]:
    """Bóc tách danh sách link bài viết từ trang danh mục VITA."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)

        if not href.endswith(".html"):
            continue
        if len(title) < 20:
            continue
        # Link bài viết chi tiết thường có dạng /vi/news/...-id.html
        if "/vi/news/" not in href and "/vi/articles/" not in href:
            continue

        abs_url = urljoin(BASE_URL, href)
        if abs_url in seen_urls:
            continue

        seen_urls.add(abs_url)
        articles.append({"title": title, "url": abs_url})

    return articles


def parse_vita_article_record(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách chi tiết bài viết chính sách du lịch & hàng không của VITA."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề
    h1 = soup.find("h1")
    og_title = soup.find("meta", property="og:title")
    headline = (h1.get_text(strip=True) if h1 else (og_title.get("content") if og_title else fallback_title)).strip()
    if not headline:
        return None

    # 2. Ngày đăng
    date_str = ""
    for el in soup.find_all(["span", "div", "p"]):
        txt = el.get_text(strip=True)
        if re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", txt) and len(txt) < 40:
            date_str = txt
            break

    published_at = parse_vita_date(date_str) if date_str else dt.datetime.now(dt.timezone.utc)

    # 3. Nội dung văn bản
    content_div = soup.find("div", class_="media-content") or soup.find("div", class_="media-content-body")
    if not content_div:
        content_div = soup.find("div", class_=lambda c: c and "content" in c.lower())

    body = content_div.get_text(separator="\n", strip=True) if content_div else None
    if not body or len(body) < 80:
        return None

    # 4. Tóm tắt
    p_tags = content_div.find_all("p") if content_div else []
    summary = p_tags[0].get_text(strip=True) if p_tags and len(p_tags[0].get_text(strip=True)) > 30 else body[:300]

    # 5. Metadata phân loại
    doc_type, doc_number, issuing_body = extract_vita_doc_metadata(headline, body)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "vita",
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


def write_vita_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu chính sách VITA vào DuckDB staging & core với cơ chế idempotent."""
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

    con.register("df_vita_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vita_staging")
    con.unregister("df_vita_staging")

    con.register("df_vita_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_vita_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_vita_core")

    return n_written


def load_existing_vita_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL VITA đã lưu trong core.macro_policy để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vita'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_vita_crawler(
    categories: list[str] | None = None,
    start_page: int = 1,
    max_pages: int = 20,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào chính sách du lịch & hàng không từ VITA."""
    if categories is None:
        categories = list(VITA_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_vita_urls(con)

    total_discovered = 0
    total_written = 0

    for cat in categories:
        logger.info(f"=== Bắt đầu cào VITA: {cat} (Trang {start_page}..{max_pages}) ===")
        cat_written = 0

        # Nếu chuyên mục không phải news thì thường chỉ có 1 trang tĩnh
        pages_to_run = max_pages if cat == "news" else 1

        for page in range(start_page, pages_to_run + 1):
            page_url = build_vita_page_url(cat, page)
            logger.info(f"[VITA - {cat}] Đang tải trang {page}/{pages_to_run}: {page_url}")
            time.sleep(delay_seconds)

            try:
                resp = session.get(page_url, timeout=15)
                if resp.status_code == 404:
                    logger.info(f"[VITA - {cat}] Trang {page} trả về 404. Kết thúc.")
                    break
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.warning(f"[VITA - {cat}] Lỗi khi tải trang {page}: {e}")
                break

            articles = parse_vita_listing(html)
            if not articles:
                logger.info(f"[VITA - {cat}] Trang {page} không có bài viết mới.")
                break

            total_discovered += len(articles)
            new_articles = [a for a in articles if a["url"] not in existing_urls]

            if not new_articles:
                logger.info(f"[VITA - {cat}] Trang {page}: Toàn bộ {len(articles)} bài đã có trong DB.")
                continue

            records = []
            for art in new_articles:
                time.sleep(delay_seconds)
                try:
                    art_resp = session.get(art["url"], timeout=15)
                    if art_resp.status_code != 200:
                        continue
                    rec = parse_vita_article_record(art_resp.text, art["url"], fallback_title=art["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(art["url"])
                except Exception as e:
                    logger.warning(f"Lỗi tải bài viết VITA {art['url']}: {e}")

            if records:
                df_page = pd.DataFrame(records)
                n_written = write_vita_macro_policy(con, df_page)
                cat_written += n_written
                total_written += n_written
                logger.info(
                    f"[VITA - {cat}] Trang {page:2d}: {len(records)} bài bóc tách thành công, +{n_written} lưu vào DB (Tổng mục: {cat_written})"
                )

        logger.info(f"=== Chuyên mục {cat} hoàn tất: +{cat_written} bản ghi lưu mới ===")

    con.close()

    return {
        "categories": categories,
        "total_discovered": total_discovered,
        "total_written": total_written,
        "start_page": start_page,
        "max_pages": max_pages,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Bộ cào chính sách & thông tin du lịch VITA (vita.vn)")
    parser.add_argument("--categories", nargs="+", default=list(VITA_CATEGORIES.keys()), help="Danh mục cào")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu (mặc định: 1)")
    parser.add_argument("--max-pages", type=int, default=20, help="Số trang tối đa (mặc định: 20)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ request (giây)")
    parser.add_argument("--db", default="db/vesta.duckdb", help="File DuckDB")
    args = parser.parse_args()

    summary = run_vita_crawler(
        categories=args.categories,
        start_page=args.start_page,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        db_path=args.db,
    )
    print("\n=== Tổng kết cào dữ liệu Hiệp hội Du lịch VITA ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
