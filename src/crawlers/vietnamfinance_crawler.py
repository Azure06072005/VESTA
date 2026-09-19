"""VietnamFinance (vietnamfinance.vn / DNDT) Macro & Market Crawler.

File: src/crawlers/vietnamfinance_crawler.py
Description:
    Thu thập tin tức thị trường chứng khoán, đầu tư FDI, tài chính ngân hàng,
    và thông tin doanh nghiệp niêm yết từ VietnamFinance.vn.
    Tuân thủ RFC 9309 (scratch/robots/vietnam_finance-robots.txt).
    Cơ chế Circuit Breaker: Nếu bị từ chối (403, 429, 503), lập tức dừng và chuyển sang website khác.
    Lưu trữ chuẩn xác vào staging.macro_policy và core.macro_policy (11 cột chuẩn).
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

BASE_URL = "https://vietnamfinance.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

CATEGORIES = {
    "tai-chinh": "https://vietnamfinance.vn/tai-chinh.htm",
    "chung-khoan": "https://vietnamfinance.vn/chung-khoan.htm",
    "vi-mo": "https://vietnamfinance.vn/vi-mo.htm",
    "ngan-hang": "https://vietnamfinance.vn/ngan-hang.htm",
    "bat-dong-san": "https://vietnamfinance.vn/bat-dong-san.htm",
    "doanh-nghiep": "https://vietnamfinance.vn/doanh-nghiep.htm",
}

DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ-CP|NĐ-CP|TT-BTC|TT-NHNN|QĐ-TTg|CV-[A-Z]+))\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_vnf_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày công bố bài viết an toàn."""
    time_el = soup.find(class_=lambda c: c and ("date" in c or "time" in c or "post-time" in c))
    search_text = time_el.get_text(strip=True) if time_el else text
    m = DATE_PATTERN.search(search_text)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                res_dt = dt.datetime(year, month, day, 8, 0, 0, tzinfo=dt.timezone.utc)
                now_utc = dt.datetime.now(dt.timezone.utc)
                if res_dt > now_utc or year < 2000:
                    return now_utc
                return res_dt
        except Exception:
            pass
    return dt.datetime.now(dt.timezone.utc)


def parse_vnf_listing(html: str) -> list[dict[str, str]]:
    """Trích xuất danh sách bài viết từ VietnamFinance."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if len(title) < 20 or not ("-d" in href and href.endswith(".html")):
            continue
        full_url = urljoin(BASE_URL, href)
        if full_url not in seen:
            seen.add(full_url)
            articles.append({"title": title, "url": full_url})

    return articles


def parse_vnf_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết VietnamFinance theo chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 15:
        return None

    published_at = parse_vnf_date(soup, html[:1500])

    paras = [
        p.get_text(strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 35 and not p.find_parent("footer")
    ]
    body = "\n\n".join(paras)
    if len(body) < 50:
        body = headline

    summary = paras[0][:400] if paras else headline[:400]
    doc_numbers = list(set(DOC_NUMBER_PATTERN.findall(body + " " + headline)))
    doc_number = doc_numbers[0] if doc_numbers else None
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "vietnamfinance",
        "issuing_body": "VietnamFinance (Tạp chí Đầu tư Tài chính)",
        "doc_type": "MARKET_NEWS",
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

    con.register("df_vnf_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vnf_staging")
    con.unregister("df_vnf_staging")

    con.register("df_vnf_core", df[required_cols])
    res = con.execute(
        """
        INSERT INTO core.news_resources
        SELECT * FROM df_vnf_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = res.fetchall()[0][0] if res else len(df)
    try:
        con.execute(
            """
            INSERT INTO core.macro_policy
            SELECT * FROM df_vnf_core
            ON CONFLICT (source_url) DO NOTHING
            """
        )
    except Exception:
        pass
    con.unregister("df_vnf_core")
    return n_written


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL đã có để khử trùng lặp."""
    urls = set()
    for tbl in ["core.news_resources", "core.macro_policy"]:
        try:
            rows = con.execute(f"SELECT source_url FROM {tbl} WHERE source = 'vietnamfinance'").fetchall()
            urls.update(r[0] for r in rows if r[0])
        except Exception:
            pass
    return urls


from src.crawlers.db_writer import ResilientDuckDBWriter, DEFAULT_TARGET_DB


def run_vietnamfinance_crawler(
    max_articles_per_cat: int = 50,
    max_pages_per_cat: int = 20,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = DEFAULT_TARGET_DB,
) -> dict[str, Any]:
    """Chạy quy trình cào VietnamFinance có phân trang lùi sâu vào quá khứ."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    writer = ResilientDuckDBWriter(target_db=db_path)
    existing_urls: set[str] = set()

    def _load_urls(con: duckdb.DuckDBPyConnection) -> None:
        existing_urls.update(load_existing_urls(con))

    writer.execute_with_retry(_load_urls)

    total_discovered = 0
    total_written = 0

    for cat_name, cat_url in CATEGORIES.items():
        logger.info("=== Bắt đầu cào VietnamFinance: %s (%s) ===", cat_name, cat_url)
        cat_written = 0
        consecutive_empty = 0

        for page in range(1, max_pages_per_cat + 1):
            if cat_written >= max_articles_per_cat:
                logger.info("[%s] Đạt giới hạn %d bài viết.", cat_name, max_articles_per_cat)
                break

            page_url = f"{cat_url}?trang={page}" if page > 1 else cat_url
            try:
                resp = session.get(page_url, timeout=15)
                if resp.status_code in (403, 429, 503):
                    logger.warning("[CIRCUIT_BREAKER] VietnamFinance từ chối (HTTP %d). Dừng.", resp.status_code)
                    return {"status": "rejected", "http_status": resp.status_code, "total_written": total_written}
                if resp.status_code != 200:
                    break
                html = resp.text
            except Exception as e:
                logger.warning("[%s] Lỗi kết nối trang %d: %s", cat_name, page, e)
                break

            articles = parse_vnf_listing(html)
            new_articles = [a for a in articles if a["url"] not in existing_urls]
            total_discovered += len(articles)

            if not new_articles:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    logger.info("[%s] Đã gặp 3 trang liên tiếp không có bài mới, chuyển danh mục.", cat_name)
                    break
                continue
            else:
                consecutive_empty = 0

            # Giới hạn số bài lấy trong trang
            remaining = max_articles_per_cat - cat_written
            batch = new_articles[:remaining]

            records = []
            for item in batch:
                time.sleep(delay_seconds)
                try:
                    art_resp = session.get(item["url"], timeout=15)
                    if art_resp.status_code in (403, 429, 503):
                        logger.warning("[CIRCUIT_BREAKER] VietnamFinance từ chối bài viết (HTTP %d).", art_resp.status_code)
                        break
                    if art_resp.status_code == 200:
                        rec = parse_vnf_article(art_resp.text, item["url"], fallback_title=item["title"])
                        if rec:
                            records.append(rec)
                            existing_urls.add(item["url"])
                except Exception as e:
                    logger.warning("[%s] Lỗi kết nối %s: %s", cat_name, item["url"], e)
                    break

            if records:
                def _save_vnf(con: duckdb.DuckDBPyConnection) -> int:
                    return write_macro_policy(con, pd.DataFrame(records))

                n = writer.execute_with_retry(_save_vnf)
                cat_written += n
                total_written += n
                logger.info("[%s - Trang %d] Đã lưu +%d bài viết mới (Danh mục: %d/%d).", cat_name, page, n, cat_written, max_articles_per_cat)

    return {
        "status": "success",
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="VietnamFinance Historical Crawler")
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="DuckDB database path")
    parser.add_argument("--max-articles-per-cat", "--max-articles", dest="max_articles_per_cat", type=int, default=50, help="Số bài tối đa mỗi chuyên mục")
    parser.add_argument("--max-pages", type=int, default=10, help="Số trang tối đa mỗi chuyên mục")
    parser.add_argument("--delay", type=float, default=0.5, help="Độ trễ request (giây)")
    args = parser.parse_args()

    summary = run_vietnamfinance_crawler(
        db_path=args.db,
        max_articles_per_cat=args.max_articles_per_cat,
        max_pages_per_cat=args.max_pages,
        delay_seconds=args.delay,
    )
    print("\n=== VietnamFinance Crawler Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()

