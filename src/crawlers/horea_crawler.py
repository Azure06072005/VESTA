"""Hiệp hội Bất động sản TP.HCM (horea.org.vn) Real Estate Regulatory Crawler.

Thu thập các công văn kiến nghị, văn bản góp ý sửa đổi Luật Đất đai, Luật Nhà ở,
Luật Kinh doanh Bất động sản và đề xuất tháo gỡ pháp lý dự án BĐS từ HoREA.
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

BASE_URL = "https://www.horea.org.vn"
DEFAULT_DELAY_SECONDS = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Danh mục chính sách & công văn trọng yếu của HoREA
HOREA_CATEGORIES = {
    "hoat-dong-horea": "Hoạt động & Công văn kiến nghị HoREA",
    "phap-luat-bat-dong-san": "Pháp luật & Chính sách Bất động sản",
}

# Regex bóc tách số công văn HoREA (VD: 110/2026/CV-HoREA, 104/2026/CV-HoREA, 98/2026/CV-HoREA)
HOREA_DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:CV|VB|BC)-(?:HoREA|HOREA))\b",
    re.IGNORECASE,
)

# Regex phụ phát hiện các Nghị định/Nghị quyết của Chính phủ được trích dẫn trong văn bản
GOV_DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|TT)-(?:CP|TTg|BXD|BTNMT))\b",
    re.IGNORECASE,
)

# Regex bóc tách ngày đăng dạng: Ngày đăng: 03-09-2026 hoặc 03/09/2026
DATE_PATTERN = re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})")


def parse_horea_date(text: str) -> dt.datetime:
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


def extract_horea_doc_metadata(headline: str, body_text: str = "") -> tuple[str, str | None, str]:
    """Trích xuất loại văn bản, số hiệu công văn và cơ quan phát hành."""
    combined = f"{headline} {body_text[:1000]}"

    # 1. Tìm số công văn HoREA
    horea_match = HOREA_DOC_NUMBER_PATTERN.search(combined)
    if horea_match:
        doc_number = horea_match.group(1).upper().replace("HOREA", "HoREA")
    else:
        gov_match = GOV_DOC_NUMBER_PATTERN.search(combined)
        doc_number = gov_match.group(1).upper() if gov_match else None

    # 2. Phân loại tài liệu
    if doc_number and "/CV-" in doc_number:
        doc_type = "Công văn kiến nghị BĐS"
    elif doc_number and "/VB-" in doc_number:
        doc_type = "Văn bản đề xuất BĐS"
    elif re.search(r"\b(?i:tháo\s+gỡ|vướng\s+mắc|dự\s+án)\b", headline):
        doc_type = "Tháo gỡ pháp lý dự án BĐS"
    elif re.search(r"\b(?i:Luật\s+Đất\s+đai|Luật\s+Nhà\s+ở|Luật\s+Kinh\s+doanh)\b", headline):
        doc_type = "Góp ý sửa đổi Luật BĐS"
    elif re.search(r"\b(?i:Nghị\s+định|Thông\s+tư|Quyết\s+định)\b", headline):
        doc_type = "Chính sách pháp luật BĐS"
    else:
        doc_type = "Chính sách BĐS & Đô thị"

    issuing_body = "Hiệp hội Bất động sản TP.HCM (HoREA)"

    return doc_type, doc_number, issuing_body


def build_horea_page_url(cat_slug: str, page: int) -> str:
    """Tạo URL phân trang theo cấu trúc của website HoREA."""
    if page == 1:
        return f"{BASE_URL}/{cat_slug}.html"
    return f"{BASE_URL}/{cat_slug}/pages-{page}.html"


def parse_horea_listing(html: str, cat_slug: str) -> list[dict[str, str]]:
    """Bóc tách danh sách link bài viết/công văn từ trang danh mục."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)

        if not href.endswith(".html"):
            continue
        if len(title) < 15:
            continue
        # Chỉ lấy các link thuộc chuyên mục bài viết chi tiết
        if f"/{cat_slug}/" not in href:
            continue

        abs_url = urljoin(BASE_URL, href)
        if abs_url in seen_urls:
            continue

        seen_urls.add(abs_url)
        articles.append({"title": title, "url": abs_url})

    return articles


def parse_horea_article_record(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách chi tiết công văn / bài viết chính sách BĐS của HoREA."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề
    h1 = soup.find("h1")
    og_title = soup.find("meta", property="og:title")
    headline = (h1.get_text(strip=True) if h1 else (og_title.get("content") if og_title else fallback_title)).strip()
    if not headline:
        return None

    # 2. Ngày đăng
    date_str = ""
    for el in soup.find_all(["div", "span", "p"]):
        txt = el.get_text(strip=True)
        if "ngày đăng" in txt.lower() or "ngày" in txt.lower():
            if any(c.isdigit() for c in txt) and len(txt) < 80:
                date_str = txt
                break
    published_at = parse_horea_date(date_str) if date_str else dt.datetime.now(dt.timezone.utc)

    # 3. Nội dung công văn
    content_div = soup.find("div", class_="content_general") or soup.find("div", class_="content")
    if not content_div:
        content_div = soup.find("div", class_="detail")

    body = content_div.get_text(separator="\n", strip=True) if content_div else None
    if not body or len(body) < 80:
        return None

    # 4. Tóm tắt
    p_tags = content_div.find_all("p") if content_div else []
    summary = p_tags[0].get_text(strip=True) if p_tags and len(p_tags[0].get_text(strip=True)) > 30 else body[:300]

    # 5. Metadata phân loại
    doc_type, doc_number, issuing_body = extract_horea_doc_metadata(headline, body)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "horea",
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


def write_horea_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu chính sách HoREA vào DuckDB staging & core với cơ chế idempotent."""
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

    con.register("df_horea_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_horea_staging")
    con.unregister("df_horea_staging")

    con.register("df_horea_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_horea_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_horea_core")

    return n_written


def load_existing_horea_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL HoREA đã lưu trong core.macro_policy để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'horea'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_horea_crawler(
    categories: list[str] | None = None,
    start_page: int = 1,
    max_pages: int = 10,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào chính sách Bất động sản từ HoREA."""
    if categories is None:
        categories = list(HOREA_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_horea_urls(con)

    total_discovered = 0
    total_written = 0

    for cat in categories:
        logger.info(f"=== Bắt đầu cào HoREA: {cat} (Trang {start_page}..{max_pages}) ===")
        cat_written = 0

        for page in range(start_page, max_pages + 1):
            page_url = build_horea_page_url(cat, page)
            logger.info(f"[HoREA - {cat}] Đang tải trang {page}/{max_pages}: {page_url}")
            time.sleep(delay_seconds)

            try:
                resp = session.get(page_url, timeout=15)
                if resp.status_code == 404:
                    logger.info(f"[HoREA - {cat}] Trang {page} trả về 404. Đã chạm cuối danh mục.")
                    break
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.warning(f"[HoREA - {cat}] Lỗi khi tải trang {page}: {e}")
                break

            articles = parse_horea_listing(html, cat)
            if not articles:
                logger.info(f"[HoREA - {cat}] Trang {page} không có bài viết mới. Kết thúc chuyên mục.")
                break

            total_discovered += len(articles)
            new_articles = [a for a in articles if a["url"] not in existing_urls]

            if not new_articles:
                logger.info(f"[HoREA - {cat}] Trang {page}: Toàn bộ {len(articles)} bài đã có trong DB. Tiếp tục.")
                continue

            records = []
            for art in new_articles:
                time.sleep(delay_seconds)
                try:
                    art_resp = session.get(art["url"], timeout=15)
                    if art_resp.status_code != 200:
                        continue
                    rec = parse_horea_article_record(art_resp.text, art["url"], fallback_title=art["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(art["url"])
                except Exception as e:
                    logger.warning(f"Lỗi khi tải bài viết HoREA {art['url']}: {e}")

            if records:
                df_page = pd.DataFrame(records)
                n_written = write_horea_macro_policy(con, df_page)
                cat_written += n_written
                total_written += n_written
                logger.info(
                    f"[HoREA - {cat}] Trang {page:2d}: {len(records)} bài bóc tách thành công, +{n_written} lưu vào DB (Tổng mục: {cat_written})"
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
    parser = argparse.ArgumentParser(description="Bộ cào chính sách & công văn HoREA (horea.org.vn)")
    parser.add_argument("--categories", nargs="+", default=list(HOREA_CATEGORIES.keys()), help="Danh mục cào")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu (mặc định: 1)")
    parser.add_argument("--max-pages", type=int, default=10, help="Số trang tối đa mỗi mục (mặc định: 10)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ request (giây)")
    parser.add_argument("--db", default="db/vesta.duckdb", help="File DuckDB")
    args = parser.parse_args()

    summary = run_horea_crawler(
        categories=args.categories,
        start_page=args.start_page,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        db_path=args.db,
    )
    print("\n=== Tổng kết cào dữ liệu HoREA ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
