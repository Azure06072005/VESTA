"""Hiệp hội Bia - Rượu - Nước giải khát Việt Nam (vba.com.vn) FMCG & Excise Tax Regulatory Crawler.

Thu thập các công văn kiến nghị, ý kiến đóng góp chính sách thuế tiêu thụ đặc biệt (TTĐB),
quy định dán nhãn, an toàn thực phẩm và trách nhiệm mở rộng của nhà sản xuất (EPR) từ VBA.
Tác động trực tiếp lên các mã cổ phiếu ngành đồ uống & hàng tiêu dùng thiết yếu (SAB, BHN, MSN).
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

BASE_URL = "https://vba.com.vn"
DEFAULT_DELAY_SECONDS = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Danh mục chính sách, hoạt động và thị trường trọng yếu của VBA
VBA_CATEGORIES = {
    "chinh-sach-1": "Chính sách thuế & Quản lý ngành đồ uống",
    "doanh-nghiep": "Hoạt động doanh nghiệp ngành đồ uống (SAB, BHN, MSN)",
    "hoat-dong-hiep-hoi": "Hoạt động & Công văn hiệp hội VBA",
    "tin-tuc": "Tin tức thị trường đồ uống & FMCG",
}

# Regex bóc tách số công văn VBA (VD: 73/CV-VBA, 15/2024/CV-VBA, 22/BC-VBA)
VBA_DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:CV|VB|BC)-(?:VBA|Hiệp\s*hội))\b",
    re.IGNORECASE,
)

# Regex phát hiện văn bản quy phạm pháp luật được trích dẫn (Nghị quyết, Nghị định, Luật TTĐB)
GOV_DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|TT|CT)-(?:CP|TTg|BTC|BCT|BYT))\b",
    re.IGNORECASE,
)

# Regex bóc tách thời gian dạng: 10/08/2026 - 10:16 PM hoặc 10/08/2026
VBA_DATETIME_PATTERN = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s*-\s*(\d{1,2}):(\d{1,2})\s*(AM|PM)?)?",
    re.IGNORECASE,
)


def parse_vba_datetime(text: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày giờ trên VBA thành UTC datetime."""
    match = VBA_DATETIME_PATTERN.search(text)
    if not match:
        return dt.datetime.now(dt.timezone.utc)

    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    raw_hour = int(match.group(4)) if match.group(4) else 8
    minute = int(match.group(5)) if match.group(5) else 0
    ampm = match.group(6).upper() if match.group(6) else None

    hour = raw_hour
    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0

    try:
        local_dt = dt.datetime(year, month, day, hour, minute, 0)
        vn_tz = dt.timezone(dt.timedelta(hours=7))
        return local_dt.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def extract_vba_doc_metadata(headline: str, body_text: str = "") -> tuple[str, str | None, str]:
    """Trích xuất số văn bản, phân loại tài liệu và cơ quan ban hành."""
    combined = f"{headline} {body_text[:1000]}"

    # 1. Tìm số công văn VBA
    vba_match = VBA_DOC_NUMBER_PATTERN.search(combined)
    if vba_match:
        doc_number = vba_match.group(1).upper().replace("HIỆP HỘI", "VBA").replace("HIỆPHỘI", "VBA")
    else:
        gov_match = GOV_DOC_NUMBER_PATTERN.search(combined)
        doc_number = gov_match.group(1).upper() if gov_match else None

    # 2. Phân loại tài liệu
    if doc_number and "/CV-" in doc_number:
        doc_type = "Công văn kiến nghị VBA"
    elif re.search(r"\b(?i:thuế\s+tiêu\s+thụ\s+đặc\s+biệt|TTĐB|nước\s+ngọt|đồ\s+uống\s+có\s+đường)\b", combined):
        doc_type = "Kiến nghị thuế tiêu thụ đặc biệt"
    elif re.search(r"\b(?i:an\s+toàn\s+thực\s+phẩm|môi\s+trường|EPR|tái\s+chế|bao\s+bì)\b", combined):
        doc_type = "Chính sách ATTP & môi trường"
    elif re.search(r"\b(?i:Sabeco|Habeco|Masan|Heineken|SAB|BHN|MSN)\b", combined):
        doc_type = "Tin tức doanh nghiệp đồ uống"
    elif re.search(r"\b(?i:hội\s+thảo|đại\s+hội|kỷ\s+niệm|tọa\s+đàm)\b", headline):
        doc_type = "Hoạt động hiệp hội VBA"
    else:
        doc_type = "Chính sách ngành đồ uống & FMCG"

    issuing_body = "Hiệp hội Bia - Rượu - Nước giải khát Việt Nam (VBA)"

    return doc_type, doc_number, issuing_body


def build_vba_page_url(cat_slug: str, page: int) -> str:
    """Tạo URL phân trang theo cấu trúc chuẩn của vba.com.vn."""
    if page == 1:
        return f"{BASE_URL}/{cat_slug}.html"
    return f"{BASE_URL}/{cat_slug}/p-{page}.html"


def parse_vba_listing(html: str) -> list[dict[str, str]]:
    """Bóc tách danh sách link bài viết từ trang danh mục VBA."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls = set()

    # Bóc tách từ các khối bài viết trong danh mục
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)

        if not href.endswith(".html"):
            continue
        if len(title) < 20:
            continue
        # Bỏ qua các trang danh mục hoặc giới thiệu
        if any(skip in href for skip in ["/chinh-sach-", "/hoat-dong-", "/doanh-nghiep", "/tin-tuc", "/gioi-thieu", "/lien-he"]):
            if not any(k in href for k in ["/chinh-sach-1.html", "/tin-tuc.html", "/tin-tuc-hoat-dong.html", "/doanh-nghiep.html"]):
                continue

        abs_url = urljoin(BASE_URL, href)
        if abs_url in seen_urls:
            continue

        # Đảm bảo đây là link bài viết (thường có slug dài dạng tin-tuc-bai-viet.html)
        slug_part = abs_url.rstrip("/").split("/")[-1].replace(".html", "")
        if len(slug_part.split("-")) < 3:
            continue

        seen_urls.add(abs_url)
        articles.append({"title": title, "url": abs_url})

    return articles


def parse_vba_article_record(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách chi tiết văn bản / tin tức chính sách đồ uống của VBA."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề
    title_div = soup.find("div", class_="box-title-main")
    h1 = soup.find("h1")
    og_title = soup.find("meta", property="og:title")
    headline = (
        title_div.get_text(strip=True)
        if title_div
        else (h1.get_text(strip=True) if h1 else (og_title.get("content") if og_title else fallback_title))
    ).strip()

    if not headline:
        return None

    # 2. Thời gian đăng
    date_str = ""
    view_header = soup.find("div", class_=lambda c: c and "view-header" in c)
    if view_header:
        date_str = view_header.get_text(strip=True)
    else:
        for el in soup.find_all(["div", "span", "p"]):
            txt = el.get_text(strip=True)
            if any(k in txt for k in ["/202", "/201"]) and len(txt) < 50:
                date_str = txt
                break

    published_at = parse_vba_datetime(date_str) if date_str else dt.datetime.now(dt.timezone.utc)

    # 3. Nội dung văn bản
    content_div = soup.find("div", class_="wrap-blog-detail-main") or soup.find("div", class_="detail-content")
    if not content_div:
        content_div = soup.find("div", class_=lambda c: c and "content" in c.lower())

    body = content_div.get_text(separator="\n", strip=True) if content_div else None
    if not body or len(body) < 80:
        return None

    # 4. Tóm tắt
    p_tags = content_div.find_all("p") if content_div else []
    summary = p_tags[0].get_text(strip=True) if p_tags and len(p_tags[0].get_text(strip=True)) > 30 else body[:300]

    # 5. Metadata phân loại
    doc_type, doc_number, issuing_body = extract_vba_doc_metadata(headline, body)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "vba",
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


def write_vba_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu chính sách VBA vào DuckDB staging & core với cơ chế idempotent."""
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

    con.register("df_vba_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vba_staging")
    con.unregister("df_vba_staging")

    con.register("df_vba_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_vba_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_vba_core")

    return n_written


def load_existing_vba_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL VBA đã lưu trong core.macro_policy để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vba'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_vba_crawler(
    categories: list[str] | None = None,
    start_page: int = 1,
    max_pages: int = 15,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào chính sách đồ uống & thuế TTĐB từ VBA."""
    if categories is None:
        categories = list(VBA_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_vba_urls(con)

    total_discovered = 0
    total_written = 0

    for cat in categories:
        logger.info(f"=== Bắt đầu cào VBA: {cat} (Trang {start_page}..{max_pages}) ===")
        cat_written = 0

        for page in range(start_page, max_pages + 1):
            page_url = build_vba_page_url(cat, page)
            logger.info(f"[VBA - {cat}] Đang tải trang {page}/{max_pages}: {page_url}")
            time.sleep(delay_seconds)

            try:
                resp = session.get(page_url, timeout=15)
                if resp.status_code == 404:
                    logger.info(f"[VBA - {cat}] Trang {page} trả về 404. Kết thúc chuyên mục.")
                    break
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.warning(f"[VBA - {cat}] Lỗi khi tải trang {page}: {e}")
                break

            articles = parse_vba_listing(html)
            if not articles:
                logger.info(f"[VBA - {cat}] Trang {page} không có bài viết mới. Kết thúc chuyên mục.")
                break

            total_discovered += len(articles)
            new_articles = [a for a in articles if a["url"] not in existing_urls]

            if not new_articles:
                logger.info(f"[VBA - {cat}] Trang {page}: Toàn bộ {len(articles)} bài đã có trong DB. Tiếp tục.")
                continue

            records = []
            for art in new_articles:
                time.sleep(delay_seconds)
                try:
                    art_resp = session.get(art["url"], timeout=15)
                    if art_resp.status_code != 200:
                        continue
                    rec = parse_vba_article_record(art_resp.text, art["url"], fallback_title=art["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(art["url"])
                except Exception as e:
                    logger.warning(f"Lỗi khi tải bài viết VBA {art['url']}: {e}")

            if records:
                df_page = pd.DataFrame(records)
                n_written = write_vba_macro_policy(con, df_page)
                cat_written += n_written
                total_written += n_written
                logger.info(
                    f"[VBA - {cat}] Trang {page:2d}: {len(records)} bài bóc tách thành công, +{n_written} lưu vào DB (Tổng mục: {cat_written})"
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
    parser = argparse.ArgumentParser(description="Bộ cào chính sách & công văn VBA (vba.com.vn)")
    parser.add_argument("--categories", nargs="+", default=list(VBA_CATEGORIES.keys()), help="Danh mục cào")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu (mặc định: 1)")
    parser.add_argument("--max-pages", type=int, default=15, help="Số trang tối đa mỗi mục (mặc định: 15)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ request (giây)")
    parser.add_argument("--db", default="db/vesta.duckdb", help="File DuckDB")
    args = parser.parse_args()

    summary = run_vba_crawler(
        categories=args.categories,
        start_page=args.start_page,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        db_path=args.db,
    )
    print("\n=== Tổng kết cào dữ liệu VBA ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
