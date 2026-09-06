"""Hiệp hội Dữ liệu Quốc gia (nda.org.vn) National Data & Digital Infrastructure Policy Crawler.

Thu thập các văn bản quy phạm pháp luật, nghị định về cơ sở dữ liệu quốc gia,
chính sách chia sẻ và chuẩn hóa dữ liệu, an toàn thông tin và hạ tầng điện toán đám mây từ Hiệp hội Dữ liệu Quốc gia (NDA).
Tác động trực tiếp lên các mã cổ phiếu ngành công nghệ, hạ tầng số & viễn thông (FPT, CTR, ELC, CMG, ITD).
Lưu trữ vào `staging.macro_policy` và `core.macro_policy` với khóa chính `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import logging
import re
import time
from typing import Any
import unicodedata

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://nda.org.vn"
DEFAULT_DELAY_SECONDS = 0.5
DEFAULT_BATCH_SIZE = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Regex bóc tách số hiệu văn bản (VD: 47/2024/NĐ-CP, 06/ĐA-CP, 13/2023/NĐ-CP, 86/2024/NQ-CP)
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+[-/\w]*(?:NĐ-CP|NQ-CP|QĐ-TTg|CT-TTg|TT-BCA|TT-BTTTT|ĐA-CP|QĐ-BCA)[-/a-zA-Z0-9]*)\b",
    re.IGNORECASE,
)


def parse_nda_datetime(date_str: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày ISO hoặc định dạng Việt Nam thành UTC datetime."""
    if not date_str:
        return dt.datetime.now(dt.timezone.utc)

    # Thử parse ISO format (VD: 2026-09-04T10:10:23.9398549)
    try:
        clean_str = date_str.split(".")[0]
        parsed = dt.datetime.fromisoformat(clean_str)
        if parsed.tzinfo is None:
            vn_tz = dt.timezone(dt.timedelta(hours=7))
            return parsed.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        pass

    # Thử định dạng dd/mm/yyyy
    date_match = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", date_str)
    if date_match:
        d, m, y = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        try:
            local_dt = dt.datetime(y, m, d, 8, 0, 0)
            vn_tz = dt.timezone(dt.timedelta(hours=7))
            return local_dt.replace(tzinfo=vn_tz).astimezone(dt.timezone.utc)
        except Exception:
            pass

    return dt.datetime.now(dt.timezone.utc)


def extract_nda_doc_metadata(headline: str, body_text: str = "") -> tuple[str, str | None, str]:
    """Phân loại chính sách dữ liệu số, số hiệu văn bản và cơ quan ban hành."""
    combined = f"{headline} {body_text[:1200]}"

    num_match = DOC_NUMBER_PATTERN.search(combined)
    doc_number = num_match.group(1).strip() if num_match else None

    # Phân loại tài liệu
    if re.search(r"\b(?i:trung\s+tâm\s+dữ\s+liệu|data\s+center|điện\s+toán\s+đám\s+mây|cloud|CTR|CMG|FPT)\b", combined):
        doc_type = "Hạ tầng trung tâm dữ liệu & điện toán đám mây"
    elif re.search(r"\b(?i:an\s+toàn\s+thông\s+tin|bảo\s+vệ\s+dữ\s+liệu|an\s+ninh\s+mạng|cybersecurity)\b", combined):
        doc_type = "Chính sách an toàn thông tin & bảo vệ dữ liệu cá nhân"
    elif re.search(r"\b(?i:kết\s+nối|chia\s+sẻ\s+dữ\s+liệu|chuẩn\s+hóa|liên\s+thông|CSDL\s+quốc\s+gia)\b", combined):
        doc_type = "Quy chuẩn kết nối & đồng bộ dữ liệu quốc gia"
    elif re.search(r"\b(?i:chuyển\s+đổi\s+số|Đề\s+án\s+06|thủ\s+tục\s+hành\s+chính|dịch\s+vụ\s+công)\b", combined):
        doc_type = "Chính sách chuyển đổi số quốc gia & Đề án 06"
    else:
        doc_type = "Chính sách & hoạt động dữ liệu quốc gia"

    # Cơ quan ban hành
    if re.search(r"\b(?i:chính\s+phủ|thủ\s+tướng)\b", combined) or (doc_number and ("-CP" in doc_number or "-TTG" in doc_number)):
        issuing_body = "Chính phủ"
    elif re.search(r"\b(?i:bộ\s+công\s+an)\b", combined) or (doc_number and "-BCA" in doc_number):
        issuing_body = "Bộ Công an"
    elif re.search(r"\b(?i:bộ\s+thông\s+tin\s+và\s+truyền\s+thông)\b", combined) or (doc_number and "-BTTTT" in doc_number):
        issuing_body = "Bộ Thông tin và Truyền thông"
    else:
        issuing_body = "Hiệp hội Dữ liệu Quốc gia"

    return doc_type, doc_number, issuing_body


def clean_html_text(raw_html: str) -> str:
    """Làm sạch HTML thành văn bản thuần có cấu trúc."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = html_lib.unescape(text)
    return unicodedata.normalize("NFC", text)


def parse_nda_api_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Bóc tách một bài viết / chính sách từ payload JSON của NDA API."""
    raw_title = item.get("tile") or item.get("title") or ""
    headline = html_lib.unescape(raw_title).strip()
    headline = unicodedata.normalize("NFC", headline)

    if not headline or len(headline) < 10:
        return None

    # URL nguồn
    slug = item.get("link") or item.get("slug") or item.get("id")
    if slug.startswith("http"):
        source_url = slug
    elif slug.startswith("/"):
        source_url = f"{BASE_URL}{slug}"
    else:
        source_url = f"{BASE_URL}/bai-viet/{slug}"

    # Nội dung & tóm tắt
    raw_content = item.get("content") or ""
    body = clean_html_text(raw_content)

    raw_desc = item.get("description") or ""
    desc_clean = clean_html_text(raw_desc)

    if not body or len(body) < 30:
        body = desc_clean or headline

    summary = desc_clean if len(desc_clean) > 20 else headline

    # Ngày phát hành
    pub_date_raw = item.get("publishDate") or item.get("date") or ""
    published_at = parse_nda_datetime(pub_date_raw)

    # Metadata phân loại
    doc_type, doc_num, issuing_body = extract_nda_doc_metadata(headline, body)
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "nda",
        "issuing_body": issuing_body,
        "doc_type": doc_type,
        "doc_number": doc_num,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline,
        "summary": summary,
        "body": body,
        "source_url": source_url,
        "fetched_at": now,
    }


def write_nda_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu chính sách dữ liệu số vào DuckDB staging & core với cơ chế idempotent."""
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

    con.register("df_nda_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_nda_staging")
    con.unregister("df_nda_staging")

    con.register("df_nda_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_nda_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_nda_core")

    return n_written


def load_existing_nda_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL NDA đã lưu trong core.macro_policy để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'nda'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_nda_crawler(
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_items: int | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào chính sách dữ liệu số từ nda.org.vn."""
    session = requests.Session()
    session.verify = False  # Chứng chỉ SSL của nda.org.vn có thể cần bỏ qua xác thực nội bộ
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_nda_urls(con)

    total_discovered = 0
    total_written = 0

    # 1. Cào danh mục văn bản chỉ đạo / chuyên trang pháp luật
    logger.info("=== Bắt đầu cào Chuyên trang Pháp luật & Văn bản Dữ liệu Quốc gia ===")
    special_url = (
        f"{BASE_URL}/fe/special/Groupbyspecial?"
        "siteId=&id=cc929d72-8cf6-460a-992e-3dc81e21a9b1"
        "&specialId=cc929d72-8cf6-460a-992e-3dc81e21a9b1"
        "&cateId=d71dad49-32ba-4395-89a4-f6c1762c78f3&showcate=no&numbercate=&take="
    )
    try:
        resp = session.get(special_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            special_records = []
            if data and isinstance(data, list) and "specialPagelist" in data[0]:
                for doc in data[0]["specialPagelist"]:
                    rec = parse_nda_api_item(doc)
                    if rec and rec["source_url"] not in existing_urls:
                        special_records.append(rec)
                        existing_urls.add(rec["source_url"])

            if special_records:
                df_spec = pd.DataFrame(special_records)
                n_spec = write_nda_macro_policy(con, df_spec)
                total_written += n_spec
                total_discovered += len(special_records)
                logger.info(f"[Chuyên trang Pháp luật] +{n_spec} văn bản lưu thành công vào core.macro_policy.")
    except Exception as e:
        logger.warning(f"Lỗi tải chuyên trang pháp luật NDA: {e}")

    # 2. Cào toàn bộ bài viết & chính sách qua REST endpoint /fe/post/get-all
    logger.info("=== Bắt đầu cào Bài viết & Chính sách qua NDA REST API ===")
    skip = 0
    batch_idx = 1

    while True:
        api_url = f"{BASE_URL}/fe/post/get-all?type=ALL&size={batch_size}&skip={skip}"
        time.sleep(delay_seconds)

        try:
            resp = session.get(api_url, timeout=30)
            if resp.status_code != 200:
                logger.info(f"API trả về mã {resp.status_code}, kết thúc thu thập.")
                break

            payload = resp.json()
            items = payload.get("items", [])
            total_count = payload.get("count", 0)

            if not items:
                logger.info("Đã duyệt hết danh sách bài viết từ API.")
                break

            total_discovered += len(items)
            page_records = []

            for it in items:
                rec = parse_nda_api_item(it)
                if rec and rec["source_url"] not in existing_urls:
                    page_records.append(rec)
                    existing_urls.add(rec["source_url"])

            if page_records:
                df_batch = pd.DataFrame(page_records)
                n_written = write_nda_macro_policy(con, df_batch)
                total_written += n_written
                logger.info(
                    f"[NDA API] Đợt {batch_idx:2d} (skip={skip:3d}): {len(page_records)} bản ghi bóc tách, "
                    f"+{n_written} lưu vào DB (Tổng: {total_written}/{total_count})"
                )
            else:
                logger.info(f"[NDA API] Đợt {batch_idx:2d} (skip={skip:3d}): Toàn bộ {len(items)} bài đã có trong DB.")

            # Kiểm tra điều kiện dừng
            if max_items and total_written >= max_items:
                logger.info(f"Đã đạt giới hạn max_items={max_items}, dừng crawl.")
                break

            if len(items) < batch_size or (skip + len(items)) >= total_count:
                logger.info("Đã đến bài viết cuối cùng.")
                break

            skip += len(items)
            batch_idx += 1

        except Exception as e:
            logger.warning(f"Lỗi cào NDA API đợt {batch_idx} (skip={skip}): {e}")
            break

    con.close()

    return {
        "total_discovered": total_discovered,
        "total_written": total_written,
        "total_pages": batch_idx,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Bộ cào dữ liệu & chính sách số Hiệp hội Dữ liệu Quốc gia (nda.org.vn)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Kích thước batch (mặc định: 50)")
    parser.add_argument("--max-items", type=int, default=None, help="Số bản ghi tối đa cần cào")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Độ trễ request (giây)")
    parser.add_argument("--db", default="db/vesta.duckdb", help="File DuckDB")
    args = parser.parse_args()

    summary = run_nda_crawler(
        batch_size=args.batch_size,
        max_items=args.max_items,
        delay_seconds=args.delay,
        db_path=args.db,
    )
    print("\n=== Tổng kết cào dữ liệu Hiệp hội Dữ liệu Quốc gia ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
