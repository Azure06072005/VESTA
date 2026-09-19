"""Báo Nhân Dân (nhandan.vn) Official Government & Policy Media Crawler.

File: src/crawlers/nhandan_crawler.py
Mô tả:
    Thu thập các tin tức, nghị quyết, chỉ đạo điều hành vĩ mô, chính sách kinh tế xã hội
    từ Báo Nhân Dân (nhandan.vn).
    Tuân thủ RFC 9309, cơ chế Circuit Breaker (ngắt ngay khi bị từ chối/reject).
    Lưu trữ chuẩn 11 cột vào staging.macro_policy và core.macro_policy.
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

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger("nhandan_crawler")

BASE_URL = "https://nhandan.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ-TW|NQ-CP|NĐ-CP|QĐ-TTg|KL-TW))\b",
    re.IGNORECASE,
)


def parse_nhandan_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày giờ công bố bài viết an toàn."""
    time_tag = soup.find("time") or soup.find(class_=lambda c: c and ("date" in c or "time" in c))
    search_text = time_tag.get_text(strip=True) if time_tag else text
    m = DATE_PATTERN.search(search_text)
    if m:
        try:
            d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mth <= 12 and 1 <= d <= 31:
                res_dt = dt.datetime(y, mth, d, 8, 0, 0, tzinfo=dt.timezone.utc)
                now_utc = dt.datetime.now(dt.timezone.utc)
                if res_dt > now_utc or y < 2000:
                    return now_utc
                return res_dt
        except Exception:
            pass
    return dt.datetime.now(dt.timezone.utc)


def parse_nhandan_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết Báo Nhân Dân chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 15:
        return None

    published_at = parse_nhandan_date(soup, html[:2000])
    paras = [
        p.get_text(strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 35 and not p.find_parent("footer")
    ]
    body = "\n\n".join(paras)
    if len(body) < 50:
        body = headline

    summary = paras[0][:400] if paras else headline[:400]
    doc_nums = list(set(DOC_NUMBER_PATTERN.findall(body + " " + headline)))
    doc_number = doc_nums[0] if doc_nums else None
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "nhandan",
        "issuing_body": "Báo Nhân Dân (Cơ quan ngôn luận Trung ương Đảng)",
        "doc_type": "OFFICIAL_PRESS",
        "doc_number": doc_number,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline[:500],
        "summary": summary,
        "body": body,
        "source_url": url,
        "fetched_at": now,
    }


def write_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Lưu bài viết vào staging.macro_policy, core.news_resources và core.macro_policy theo chuẩn 11 cột."""
    if df.empty:
        return 0

    required_cols = [
        "source", "issuing_body", "doc_type", "doc_number",
        "published_at", "available_at", "headline", "summary", "body",
        "source_url", "fetched_at"
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    con.register("df_nd_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_nd_staging")
    con.unregister("df_nd_staging")

    con.register("df_nd_core", df[required_cols])
    # Ghi vào core.news_resources
    res = con.execute(
        """
        INSERT INTO core.news_resources
        SELECT * FROM df_nd_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n = res.fetchall()[0][0] if res else len(df)
    # Đồng thời ghi vào core.macro_policy để duy trì tương thích ngược
    try:
        con.execute(
            """
            INSERT INTO core.macro_policy
            SELECT * FROM df_nd_core
            ON CONFLICT (source_url) DO NOTHING
            """
        )
    except Exception:
        pass
    con.unregister("df_nd_core")
    return n


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL đã có để khử trùng lặp."""
    urls = set()
    for tbl in ["core.news_resources", "core.macro_policy"]:
        try:
            rows = con.execute(f"SELECT source_url FROM {tbl} WHERE source = 'nhandan'").fetchall()
            urls.update(r[0] for r in rows if r[0])
        except Exception:
            pass
    return urls


def generate_sitemap_urls(start_year: int = 2026, end_year: int = 2000) -> list[tuple[int, int, str]]:
    """Tạo danh sách URL sitemap hàng tháng duyệt ngược từ năm mới nhất về quá khứ."""
    sitemaps = []
    for y in range(start_year, end_year - 1, -1):
        max_month = 9 if y == 2026 else 12
        for m in range(max_month, 0, -1):
            sitemaps.append((y, m, f"https://nhandan.vn/sitemaps/news-{y}-{m}.xml"))
    return sitemaps


from src.crawlers.db_writer import ResilientDuckDBWriter, DEFAULT_TARGET_DB


def run_nhandan_crawler(
    max_articles: int = 50,
    start_year: int = 2026,
    end_year: int = 2000,
    max_sitemaps: int = 50,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = DEFAULT_TARGET_DB,
) -> dict[str, Any]:
    """Chạy quy trình cào Báo Nhân Dân với vòng lặp sitemap duyệt lùi về quá khứ."""
    session = requests.Session()
    session.headers.update(HEADERS)

    writer = ResilientDuckDBWriter(target_db=db_path)
    existing_urls: set[str] = set()

    def _load_urls(con: duckdb.DuckDBPyConnection) -> None:
        existing_urls.update(load_existing_urls(con))

    writer.execute_with_retry(_load_urls)

    sitemaps = generate_sitemap_urls(start_year=start_year, end_year=end_year)[:max_sitemaps]
    logger.info(
        "=== Bắt đầu cào Báo Nhân Dân: duyệt %d sitemaps (%d -> %d), tối đa %d bài ===",
        len(sitemaps), start_year, end_year, max_articles
    )

    total_written = 0
    total_discovered = 0
    breaker_tripped = False

    for year, month, sm_url in sitemaps:
        if total_written >= max_articles or breaker_tripped:
            break

        logger.info("[nhandan] Đang quét sitemap %d-%02d: %s", year, month, sm_url)
        try:
            resp = session.get(sm_url, timeout=12, verify=False)
            if resp.status_code in (401, 403, 410, 429, 503):
                logger.warning("[CIRCUIT BREAKER] nhandan.vn từ chối yêu cầu (HTTP %d). Dừng.", resp.status_code)
                breaker_tripped = True
                break
            if resp.status_code != 200:
                continue

            all_locs = re.findall(r"<loc>(.*?)</loc>", resp.text)
            total_discovered += len(all_locs)

            # Ưu tiên các bài viết kinh tế, chính trị, xã hội
            urls = [
                u for u in all_locs
                if u not in existing_urls and any(cat in u for cat in ["/kinh-te/", "/chinh-tri/", "/xa-hoi/"])
            ]
            if not urls:
                urls = [u for u in all_locs if u not in existing_urls]

            # Giới hạn số lượng cần lấy
            remaining = max_articles - total_written
            urls = urls[:remaining]

            if not urls:
                logger.info("[nhandan] Sitemap %d-%02d: Tất cả bài viết đã có trong CSDL.", year, month)
                continue

            records = []
            for url in urls:
                time.sleep(delay_seconds)
                try:
                    art_resp = session.get(url, timeout=12, verify=False)
                    if art_resp.status_code in (401, 403, 410, 429, 503):
                        logger.warning("[CIRCUIT BREAKER] nhandan từ chối bài viết (HTTP %d). Dừng.", art_resp.status_code)
                        breaker_tripped = True
                        break
                    if art_resp.status_code == 200:
                        rec = parse_nhandan_article(art_resp.text, url)
                        if rec:
                            records.append(rec)
                            existing_urls.add(url)
                except Exception as e:
                    logger.warning("[nhandan] Lỗi bài viết %s: %s", url, e)
                    break

            if records:
                def _save_nd(con: duckdb.DuckDBPyConnection) -> int:
                    return write_macro_policy(con, pd.DataFrame(records))

                n = writer.execute_with_retry(_save_nd)
                total_written += n
                logger.info("[nhandan] Sitemap %d-%02d: Đã lưu +%d bài viết (Tổng: %d/%d).", year, month, n, total_written, max_articles)

        except Exception as e:
            logger.warning("[nhandan] Lỗi kết nối sitemap %s: %s. Chuyển sitemap tiếp theo.", sm_url, e)

    return {
        "status": "success" if not breaker_tripped else "partial_success",
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Bao Nhan Dan Historical Crawler")
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="DuckDB path")
    parser.add_argument("--max-articles", type=int, default=30, help="Số bài tối đa")
    parser.add_argument("--start-year", type=int, default=2026, help="Năm bắt đầu (mặc định 2026)")
    parser.add_argument("--end-year", type=int, default=2000, help="Năm kết thúc (mặc định 2000)")
    parser.add_argument("--max-sitemaps", type=int, default=50, help="Số sitemaps tối đa duyệt")
    parser.add_argument("--delay", type=float, default=0.5, help="Độ trễ giữa các request")
    args = parser.parse_args()

    res = run_nhandan_crawler(
        db_path=args.db,
        max_articles=args.max_articles,
        start_year=args.start_year,
        end_year=args.end_year,
        max_sitemaps=args.max_sitemaps,
        delay_seconds=args.delay,
    )
    print("\n=== Bao Nhan Dan Crawler Complete ===")
    for k, v in res.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()

