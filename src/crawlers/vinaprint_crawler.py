"""Hiệp hội In Việt Nam (vinaprint.com.vn) Printing & Packaging Policy Crawler.

Thu thập các văn bản quy phạm pháp luật, nghị định quản lý hoạt động in ấn,
quy chuẩn kỹ thuật bao bì, báo cáo thị trường giấy & nguyên liệu đóng gói từ Hiệp hội In Việt Nam.
Tác động trực tiếp lên các mã cổ phiếu ngành bao bì carton & sản phẩm giấy (DHC, HHP, GDT, SVI).
Lưu trữ vào `staging.macro_policy` và `core.macro_policy` với khóa chính `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import time
from typing import Any
import unicodedata
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

BASE_URL = "http://vinaprint.com.vn"
DEFAULT_DELAY_SECONDS = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Các chuyên mục chính sách, văn bản và thị trường của Hiệp hội In
VINAPRINT_CATEGORIES = {
    "van-ban-moi-sp536": {
        "id": 536,
        "name": "Văn bản mới",
        "slug": "van-ban-moi",
        "default_type": "Chính sách quản lý nhà nước về in ấn & bao bì",
    },
    "van-ban-hiep-hoi-sp537": {
        "id": 537,
        "name": "Văn bản hiệp hội",
        "slug": "van-ban-hiep-hoi",
        "default_type": "Văn bản & quy chế Hiệp hội In Việt Nam",
    },
    "du-thao-sp538": {
        "id": 538,
        "name": "Dự thảo chính sách",
        "slug": "du-thao",
        "default_type": "Dự thảo quy định ngành in & bao bì",
    },
    "thi-truong---xu-huong-sp533": {
        "id": 533,
        "name": "Thị trường & Xu hướng",
        "slug": "thi-truong---xu-huong",
        "default_type": "Thị trường & giá nguyên liệu giấy bao bì",
    },
    "tin-tuc-hiep-hoi-sp532": {
        "id": 532,
        "name": "Tin tức Hiệp hội",
        "slug": "tin-tuc-hiep-hoi",
        "default_type": "Tin tức ngành in & xuất bản Việt Nam",
    },
}

# Regex bóc tách số hiệu văn bản (VD: 60/2024/NĐ-CP, 15/2020/TT-BTTTT, 05/QĐ-HHI)
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+[-/\w]*(?:NĐ-CP|TT-BTTTT|TT-BTC|QĐ-TTg|CT-TTg|QĐ-BTTTT|QĐ-HHI|NQ-CP)[-/a-zA-Z0-9]*)\b",
    re.IGNORECASE,
)

# Regex bóc tách ngày tháng dạng: dd/mm/yyyy hoặc dd-mm-yyyy hoặc "ngày dd tháng mm năm yyyy"
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")
DATE_TEXT_PATTERN = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE)


def parse_vinaprint_date(text: str) -> dt.datetime:
    """Bóc tách ngày tháng từ văn bản hoặc chuỗi ngày."""
    if not text:
        return dt.datetime.now(dt.timezone.utc)

    # 1. Thử dạng ngày dd tháng mm năm yyyy
    match_text = DATE_TEXT_PATTERN.search(text)
    if match_text:
        day, month, year = int(match_text.group(1)), int(match_text.group(2)), int(match_text.group(3))
        try:
            local_dt = dt.datetime(year, month, day, 8, 0, 0)
            vn_tz = dt.timezone(dt.timedelta(hours=7))
            return local_dt.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
        except Exception:
            pass

    # 2. Thử dạng dd/mm/yyyy
    match = DATE_PATTERN.search(text)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            local_dt = dt.datetime(year, month, day, 8, 0, 0)
            vn_tz = dt.timezone(dt.timedelta(hours=7))
            return local_dt.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
        except Exception:
            pass

    return dt.datetime.now(dt.timezone.utc)


def extract_vinaprint_doc_metadata(headline: str, body_text: str = "", default_type: str = "") -> tuple[str, str | None, str]:
    """Phân loại tài liệu, số hiệu văn bản và cơ quan ban hành."""
    combined = f"{headline} {body_text[:1200]}"

    num_match = DOC_NUMBER_PATTERN.search(combined)
    doc_number = num_match.group(1).strip() if num_match else None

    # Phân loại tài liệu
    if re.search(r"\b(?i:bao\s+bì|carton|giấy\s+in|nguyên\s+liệu\s+giấy|bột\s+giấy|DHC|HHP)\b", combined):
        doc_type = "Thị trường bao bì & nguyên liệu giấy"
    elif re.search(r"\b(?i:nghị\s+định|thông\s+tư|quy\s+chuẩn\s+kỹ\s+thuật|tiêu\s+chuẩn)\b", combined):
        doc_type = "Chính sách quản lý nhà nước về in ấn & bao bì"
    elif re.search(r"\b(?i:điều\s+lệ|quy\s+chế|nghị\s+quyết\s+đại\s+hội)\b", combined):
        doc_type = "Văn bản & quy chế Hiệp hội In Việt Nam"
    elif default_type:
        doc_type = default_type
    else:
        doc_type = "Chính sách ngành in & bao bì"

    # Cơ quan ban hành
    if re.search(r"\b(?i:chính\s+phủ|thủ\s+tướng)\b", combined) or (doc_number and "NĐ-CP" in doc_number.upper()):
        issuing_body = "Chính phủ"
    elif re.search(r"\b(?i:bộ\s+thông\s+tin\s+và\s+truyền\s+thông|cục\s+xuất\s+bản)\b", combined):
        issuing_body = "Bộ Thông tin và Truyền thông"
    elif re.search(r"\b(?i:bộ\s+tài\s+chính|tổng\s+cục\s+thuế)\b", combined):
        issuing_body = "Bộ Tài chính"
    else:
        issuing_body = "Hiệp hội In Việt Nam"

    return doc_type, doc_number, issuing_body


def build_vinaprint_page_url(cat_key: str, page: int) -> str:
    """Sinh URL phân trang chuẩn của vinaprint.com.vn."""
    meta = VINAPRINT_CATEGORIES.get(cat_key, {})
    if page <= 1:
        return f"{BASE_URL}/{cat_key}"
    cat_id = meta.get("id", 533)
    slug = meta.get("slug", "thi-truong---xu-huong")
    return f"{BASE_URL}/product/{cat_id}/{page - 1}/{slug}.html"


def parse_vinaprint_article_record(
    html: str,
    url: str,
    fallback_title: str = "",
    default_type: str = "",
) -> dict[str, Any] | None:
    """Bóc tách chi tiết bài viết / văn bản trên vinaprint.com.vn."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề
    headline = ""
    h2 = soup.find("h2")
    if h2:
        headline = unicodedata.normalize("NFC", h2.get_text(strip=True))

    if not headline:
        title_box = soup.find("div", class_="page-title")
        if title_box:
            h_any = title_box.find(["h1", "h2", "h3", "h5"])
            if h_any:
                headline = unicodedata.normalize("NFC", h_any.get_text(strip=True))

    if not headline and fallback_title:
        headline = unicodedata.normalize("NFC", fallback_title.strip())

    if not headline or len(headline) < 10:
        return None

    # 2. Nội dung văn bản (bên trong div.detail-j, bỏ qua danh sách bài viết liên quan)
    body = ""
    detail_box = soup.find("div", class_="detail-j")
    if detail_box:
        # Xóa phần "Bài viết cùng danh mục"
        related_div = detail_box.find("div", class_="row")
        if related_div:
            related_div.decompose()
        related_h5 = detail_box.find("h5")
        if related_h5 and "bài viết cùng danh mục" in related_h5.get_text().lower():
            related_h5.decompose()

        body = unicodedata.normalize("NFC", detail_box.get_text(separator="\n", strip=True))

    if not body:
        padding_sec = soup.find("section", class_="padding-section")
        if padding_sec:
            body = unicodedata.normalize("NFC", padding_sec.get_text(separator="\n", strip=True))

    # Nếu bài viết chỉ là bản scan ảnh, tóm tắt lại từ tiêu đề
    if len(body) < 30:
        body = f"{headline}\n(Văn bản scan ảnh/đính kèm được công bố trên Cổng thông tin Hiệp hội In Việt Nam: {url})"

    # 3. Ngày phát hành / công bố
    published_at = parse_vinaprint_date(f"{headline} {body[:500]}")

    # 4. Tóm tắt
    lines = [l.strip() for l in body.split("\n") if len(l.strip()) > 30]
    summary = lines[0] if lines else headline

    # 5. Metadata phân loại
    doc_type, doc_num, issuing_body = extract_vinaprint_doc_metadata(headline, body, default_type=default_type)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "vinaprint",
        "issuing_body": issuing_body,
        "doc_type": doc_type,
        "doc_number": doc_num,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline,
        "summary": summary,
        "body": body,
        "source_url": url,
        "fetched_at": now,
    }


def write_vinaprint_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu chính sách ngành in & bao bì vào DuckDB staging & core với cơ chế idempotent."""
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

    con.register("df_vinaprint_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vinaprint_staging")
    con.unregister("df_vinaprint_staging")

    con.register("df_vinaprint_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_vinaprint_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_vinaprint_core")

    return n_written


def load_existing_vinaprint_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL vinaprint đã lưu trong core.macro_policy để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vinaprint'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_vinaprint_crawler(
    categories: list[str] | None = None,
    start_page: int = 1,
    max_pages: int = 15,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào chính sách ngành in & bao bì từ vinaprint.com.vn."""
    if categories is None:
        categories = list(VINAPRINT_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_vinaprint_urls(con)

    total_discovered = 0
    total_written = 0

    for cat_key in categories:
        meta = VINAPRINT_CATEGORIES.get(cat_key, {})
        cat_name = meta.get("name", cat_key)
        default_type = meta.get("default_type", "Chính sách ngành in & bao bì")
        logger.info(f"=== Bắt đầu cào Hiệp hội In: {cat_name} (Trang {start_page}..{max_pages}) ===")
        cat_written = 0

        for page in range(start_page, max_pages + 1):
            page_url = build_vinaprint_page_url(cat_key, page)
            time.sleep(delay_seconds)

            try:
                resp = session.get(page_url, timeout=15)
                resp.encoding = "utf-8"
                if resp.status_code != 200:
                    logger.info(f"[{cat_name}] Trang {page} trả về mã {resp.status_code}, chuyển mục kế tiếp.")
                    break
            except Exception as e:
                logger.warning(f"Lỗi tải trang danh sách {page_url}: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            page_articles = []

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "-ct" in href:
                    title = a.get_text(strip=True)
                    if len(title) > 15:
                        abs_url = urljoin(BASE_URL, href)
                        if abs_url not in existing_urls:
                            page_articles.append({"title": title, "url": abs_url})

            # Khử trùng lặp URL trong trang
            unique_articles = []
            seen_this_page = set()
            for art in page_articles:
                if art["url"] not in seen_this_page and art["url"] not in existing_urls:
                    seen_this_page.add(art["url"])
                    unique_articles.append(art)

            if not unique_articles:
                logger.info(f"[{cat_name}] Trang {page} không còn bài viết mới, kết thúc chuyên mục.")
                break

            total_discovered += len(unique_articles)
            logger.info(f"[{cat_name}] Trang {page}: Tìm thấy {len(unique_articles)} bài viết mới.")

            records = []
            for art in unique_articles:
                time.sleep(delay_seconds)
                try:
                    art_resp = session.get(art["url"], timeout=15)
                    art_resp.encoding = "utf-8"
                    if art_resp.status_code == 200:
                        rec = parse_vinaprint_article_record(
                            art_resp.text,
                            art["url"],
                            fallback_title=art["title"],
                            default_type=default_type,
                        )
                        if rec:
                            records.append(rec)
                            existing_urls.add(art["url"])
                except Exception as e:
                    logger.warning(f"Lỗi tải chi tiết bài viết {art['url']}: {e}")

            if records:
                df_page = pd.DataFrame(records)
                n_written = write_vinaprint_macro_policy(con, df_page)
                cat_written += n_written
                total_written += n_written
                logger.info(
                    f"[{cat_name}] Trang {page:2d}: {len(records)} bài bóc tách thành công, +{n_written} lưu vào DB (Tổng mục: {cat_written})"
                )

        logger.info(f"=== Chuyên mục {cat_name} hoàn tất: +{cat_written} bản ghi lưu mới ===")

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
    parser = argparse.ArgumentParser(description="Bộ cào chính sách & thị trường Hiệp hội In Việt Nam (vinaprint.com.vn)")
    parser.add_argument("--categories", nargs="+", default=list(VINAPRINT_CATEGORIES.keys()), help="Danh mục cào")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu (mặc định: 1)")
    parser.add_argument("--max-pages", type=int, default=15, help="Số trang tối đa (mặc định: 15)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ request (giây)")
    parser.add_argument("--db", default="db/vesta.duckdb", help="File DuckDB")
    args = parser.parse_args()

    summary = run_vinaprint_crawler(
        categories=args.categories,
        start_page=args.start_page,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
        db_path=args.db,
    )
    print("\n=== Tổng kết cào dữ liệu Hiệp hội In Việt Nam ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
