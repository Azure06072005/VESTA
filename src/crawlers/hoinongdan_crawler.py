"""Hội Nông dân Việt Nam (hoinongdan.org.vn) Agricultural & Agrochemical Policy Crawler.

Thu thập các văn bản chỉ đạo điều hành, công văn, quyết định, chính sách vật tư nông nghiệp,
phân bón, hỗ trợ giống cây trồng và quy định xuất khẩu nông sản từ Hội Nông dân Việt Nam.
Tác động trực tiếp lên các mã cổ phiếu ngành phân bón & nông nghiệp (DPM, DCM, BFC, PAN, LTG, HAG, TAR).
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
import unicodedata

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "http://www.hoinongdan.org.vn"
DEFAULT_DELAY_SECONDS = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Danh mục văn bản chỉ đạo điều hành chính thức
STEERING_CATEGORIES = {
    11495: "Công văn Hội Nông dân",
    11509: "Quyết định Hội Nông dân",
    11502: "Hướng dẫn chính sách & nghiệp vụ",
    11491: "Kế hoạch phát triển nông nghiệp",
    11493: "Thông báo điều hành",
    11489: "Chương trình mục tiêu nông nghiệp",
    11494: "Báo cáo ngành nông nghiệp & vật tư",
}

# Danh mục tin tức & chính sách vĩ mô ngành nông nghiệp
NEWS_CATEGORIES = {
    "chinh-sach": "Chính sách nông nghiệp & đất đai nông thôn",
    "hop-tac-xa-nong-nghiep": "Hợp tác xã & chuỗi giá trị nông nghiệp",
    "khoa-hoc-cong-nghe": "Khoa học công nghệ, phân bón & giống cây trồng",
    "tin-tuc-chinh-tri": "Thời sự & kinh tế nông nghiệp",
}

# Regex bóc tách số hiệu văn bản (VD: 722- CV/VP, 15/QĐ-HND, 08/HD-HND, 102/TB-HND)
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+[-/\s]*(?:CV|QĐ|HD|HĐ|KH|TB|CT|BC|NQ)[-/a-zA-Z0-9]*)\b",
    re.IGNORECASE,
)

# Regex bóc tách ngày tháng dạng: 26/11/2024 hoặc 28/08/2026 09:35
DATETIME_PATTERN = re.compile(
    r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:\s+(\d{1,2}):(\d{1,2}))?"
)


def parse_hnd_datetime(text: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày giờ trên hoinongdan.org.vn thành UTC datetime."""
    match = DATETIME_PATTERN.search(text)
    if not match:
        return dt.datetime.now(dt.timezone.utc)

    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour = int(match.group(4)) if match.group(4) else 8
    minute = int(match.group(5)) if match.group(5) else 0

    try:
        local_dt = dt.datetime(year, month, day, hour, minute, 0)
        vn_tz = dt.timezone(dt.timedelta(hours=7))
        return local_dt.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def extract_hnd_doc_metadata(headline: str, body_text: str = "", raw_doc_number: str | None = None) -> tuple[str, str | None, str]:
    """Trích xuất phân loại văn bản, số hiệu và cơ quan ban hành."""
    combined = f"{headline} {body_text[:1000]}"

    doc_number = raw_doc_number
    if not doc_number:
        num_match = DOC_NUMBER_PATTERN.search(combined)
        doc_number = num_match.group(1).strip() if num_match else None

    # Phân loại tài liệu
    if re.search(r"\b(?i:phân\s+bón|đạm|lân|kali|vật\s+tư\s+nông\s+nghiệp|DPM|DCM|BFC)\b", combined):
        doc_type = "Chính sách phân bón & vật tư nông nghiệp"
    elif re.search(r"\b(?i:xuất\s+khẩu\s+gạo|lúa\s+gạo|nông\s+sản|sầu\s+riêng|cà\s+phê|PAN|LTG|TAR)\b", combined):
        doc_type = "Chính sách xuất khẩu nông sản & lúa gạo"
    elif re.search(r"\b(?i:công\s+văn)\b", headline) or (doc_number and "CV" in doc_number.upper()):
        doc_type = "Công văn điều hành nông nghiệp"
    elif re.search(r"\b(?i:quyết\s+định)\b", headline) or (doc_number and "QĐ" in doc_number.upper()):
        doc_type = "Quyết định chính sách nông nghiệp"
    elif re.search(r"\b(?i:hướng\s+dẫn)\b", headline) or (doc_number and "HD" in doc_number.upper()):
        doc_type = "Hướng dẫn chính sách nông nghiệp"
    elif re.search(r"\b(?i:kế\s+hoạch)\b", headline) or (doc_number and "KH" in doc_number.upper()):
        doc_type = "Kế hoạch phát triển nông nghiệp"
    elif re.search(r"\b(?i:hợp\s+tác\s+xã|kinh\s+tế\s+tập\s+thể)\b", combined):
        doc_type = "Chính sách hợp tác xã nông nghiệp"
    else:
        doc_type = "Chính sách nông nghiệp & nông thôn"

    issuing_body = "Hội Nông dân Việt Nam"

    return doc_type, doc_number, issuing_body


def parse_steering_detail_record(html: str, url: str) -> dict[str, Any] | None:
    """Bóc tách chi tiết văn bản chỉ đạo điều hành có cấu trúc (bảng thuộc tính)."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Bóc tách các trường từ bảng thuộc tính
    table_fields: dict[str, str] = {}
    doc_number = None
    pub_date_str = ""
    signer = ""
    summary_text = ""

    for tr in soup.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) >= 2:
            key = unicodedata.normalize("NFC", tds[0].get_text(strip=True))
            val = unicodedata.normalize("NFC", tds[1].get_text(strip=True))
            if key and val and len(key) < 60:
                table_fields[key] = val
                key_lower = key.lower()
                if "số ký hiệu" in key_lower or "số văn bản" in key_lower:
                    doc_number = val
                elif "ngày ban hành" in key_lower or "ngày hiệu lực" in key_lower:
                    if not pub_date_str:
                        pub_date_str = val
                elif "trích yếu" in key_lower:
                    summary_text = val
                elif "người ký" in key_lower:
                    signer = val

    # 2. Tiêu đề
    headline = summary_text
    if not headline:
        h1 = soup.find("h1")
        detail_box = soup.find("div", class_=lambda c: c and "librarydetail" in c.lower())
        if h1:
            headline = h1.get_text(strip=True)
        elif detail_box:
            first_el = detail_box.find(["h2", "h3", "b", "strong"])
            headline = first_el.get_text(strip=True) if first_el else ""
        else:
            og_title = soup.find("meta", property="og:title")
            headline = og_title.get("content", "").strip() if og_title else ""

    if not headline or len(headline) < 10:
        return None

    published_at = parse_hnd_datetime(pub_date_str) if pub_date_str else dt.datetime.now(dt.timezone.utc)

    # 3. Nội dung văn bản
    detail_box = soup.find("div", class_=lambda c: c and "librarydetail" in c.lower())
    if detail_box and len(detail_box.get_text(strip=True)) > 80:
        body = detail_box.get_text(separator="\n", strip=True)
    elif table_fields:
        body = "\n".join([f"{k}: {v}" for k, v in table_fields.items() if v])
    else:
        body = soup.get_text(separator="\n", strip=True)

    if len(body) < 30:
        return None

    summary = summary_text or headline

    # 4. Metadata phân loại
    doc_type, doc_num, issuing_body = extract_hnd_doc_metadata(headline, body, raw_doc_number=doc_number)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "hoinongdan",
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


def parse_news_article_record(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết tin tức / phân tích chính sách nông nghiệp."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Tiêu đề
    h1 = soup.find("h1")
    title_box = soup.find(class_=lambda c: c and any(k in c.lower() for k in ["articledetail", "title", "contentbanner"]))
    headline = ""
    if h1:
        headline = h1.get_text(strip=True)
    elif soup.title and soup.title.string:
        headline = soup.title.string.strip()
    elif title_box:
        first_el = title_box.find(["h2", "h3", "b"])
        headline = first_el.get_text(strip=True) if first_el else fallback_title
    else:
        headline = fallback_title

    if not headline or len(headline) < 10:
        return None

    # 2. Ngày đăng
    date_str = ""
    for el in soup.find_all(["div", "span", "p"]):
        txt = el.get_text(strip=True)
        if any(k in txt.lower() for k in ["thứ", "ngày", "/202", "/201"]) and len(txt) < 50:
            if re.search(r"\d{1,2}/\d{1,2}/\d{4}", txt):
                date_str = txt
                break

    published_at = parse_hnd_datetime(date_str) if date_str else dt.datetime.now(dt.timezone.utc)

    # 3. Nội dung bài viết
    content_div = soup.find("div", class_="ArticleContent") or soup.find("div", class_="ArticleDetailControl")
    if not content_div:
        content_div = soup.find("div", class_=lambda c: c and "content" in c.lower())

    body = content_div.get_text(separator="\n", strip=True) if content_div else None
    if not body or len(body) < 80:
        return None

    # 4. Tóm tắt
    p_tags = content_div.find_all("p") if content_div else []
    summary = p_tags[0].get_text(strip=True) if p_tags and len(p_tags[0].get_text(strip=True)) > 30 else body[:300]

    # 5. Metadata phân loại
    doc_type, doc_number, issuing_body = extract_hnd_doc_metadata(headline, body)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "hoinongdan",
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


def write_hnd_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu chính sách Hội Nông Dân vào DuckDB staging & core với cơ chế idempotent."""
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

    con.register("df_hnd_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_hnd_staging")
    con.unregister("df_hnd_staging")

    con.register("df_hnd_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_hnd_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_hnd_core")

    return n_written


def load_existing_hnd_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL Hội Nông Dân đã lưu trong core.macro_policy để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'hoinongdan'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_hoinongdan_crawler(
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào chính sách nông nghiệp & vật tư phân bón từ Hội Nông dân VN."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_hnd_urls(con)

    total_discovered = 0
    total_written = 0

    # 1. Cào văn bản chỉ đạo điều hành (Steering documents)
    logger.info("=== Bắt đầu cào Văn bản chỉ đạo điều hành Hội Nông dân Việt Nam ===")
    for cate_id, cate_name in STEERING_CATEGORIES.items():
        cate_url = f"{BASE_URL}/?pageid=27205&p_cate={cate_id}"
        time.sleep(delay_seconds)
        try:
            resp = session.get(cate_url, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            items = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "p_steering=" in href:
                    abs_url = urljoin(BASE_URL, href)
                    if abs_url not in existing_urls:
                        items.append(abs_url)

            total_discovered += len(items)
            logger.info(f"[{cate_name}] Tìm thấy {len(items)} văn bản mới.")

            records = []
            for doc_url in items:
                time.sleep(delay_seconds)
                try:
                    doc_resp = session.get(doc_url, timeout=15)
                    doc_resp.encoding = "utf-8"
                    if doc_resp.status_code == 200:
                        rec = parse_steering_detail_record(doc_resp.text, doc_url)
                        if rec:
                            records.append(rec)
                            existing_urls.add(doc_url)
                except Exception as e:
                    logger.warning(f"Lỗi tải văn bản điều hành {doc_url}: {e}")

            if records:
                df_page = pd.DataFrame(records)
                n_written = write_hnd_macro_policy(con, df_page)
                total_written += n_written
                logger.info(f"[{cate_name}] +{n_written} văn bản lưu thành công vào core.macro_policy.")

        except Exception as e:
            logger.warning(f"Lỗi duyệt chuyên mục {cate_name}: {e}")

    # 2. Cào chuyên mục tin tức & chính sách nông nghiệp
    logger.info("=== Bắt đầu cào Chuyên mục Chính sách & Khoa học kỹ thuật nông nghiệp ===")
    for cat_slug, cat_name in NEWS_CATEGORIES.items():
        cat_url = f"{BASE_URL}/{cat_slug}"
        time.sleep(delay_seconds)
        try:
            resp = session.get(cat_url, timeout=15)
            resp.encoding = "utf-8"
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            news_items = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                title = a.get_text(strip=True)
                if f"/{cat_slug}/" in href and len(title) > 20:
                    abs_url = urljoin(BASE_URL, href)
                    if abs_url not in existing_urls:
                        news_items.append({"title": title, "url": abs_url})

            total_discovered += len(news_items)
            logger.info(f"[{cat_name}] Tìm thấy {len(news_items)} bài viết mới.")

            records = []
            for item in news_items:
                time.sleep(delay_seconds)
                try:
                    art_resp = session.get(item["url"], timeout=15)
                    art_resp.encoding = "utf-8"
                    if art_resp.status_code == 200:
                        rec = parse_news_article_record(art_resp.text, item["url"], fallback_title=item["title"])
                        if rec:
                            records.append(rec)
                            existing_urls.add(item["url"])
                except Exception as e:
                    logger.warning(f"Lỗi tải bài viết {item['url']}: {e}")

            if records:
                df_page = pd.DataFrame(records)
                n_written = write_hnd_macro_policy(con, df_page)
                total_written += n_written
                logger.info(f"[{cat_name}] +{n_written} bài viết lưu thành công vào core.macro_policy.")

        except Exception as e:
            logger.warning(f"Lỗi duyệt chuyên mục {cat_name}: {e}")

    con.close()

    logger.info(
        f"=== Hoàn tất cào Hội Nông dân VN: Tổng tìm thấy {total_discovered}, đã lưu mới {total_written} ==="
    )
    return {
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Bộ cào chính sách & vật tư nông nghiệp Hội Nông dân VN (hoinongdan.org.vn)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ request (giây)")
    parser.add_argument("--db", default="db/vesta.duckdb", help="File DuckDB")
    args = parser.parse_args()

    summary = run_hoinongdan_crawler(
        delay_seconds=args.delay,
        db_path=args.db,
    )
    print("\n=== Tổng kết cào dữ liệu Hội Nông dân Việt Nam ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
