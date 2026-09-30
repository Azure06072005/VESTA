"""Hiệp hội Ngân hàng Việt Nam (VNBA - vnba.org.vn) Policy & Banking Regulatory Crawler.

File: src/crawlers/vnba_crawler.py
Description:
    Thu thập các thông tin chỉ đạo, góp ý dự thảo luật, thông tư NHNN, nghị định
    về bảo đảm tiền vay, xử lý nợ xấu và thị trường tiền tệ từ Hiệp hội Ngân hàng (VNBA).
    Tác động trực tiếp lên các mã cổ phiếu ngân hàng VN30 và toàn ngành ngân hàng:
    VCB, BID, CTG, MBB, TCB, VPB, ACB, STB, HDB, LPB, MSB, SHB, SSB, TPB, VIB.
    Tuân thủ RFC 9309 (scratch/robots/vnba_org_vn-robots.txt).
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

BASE_URL = "https://vnba.org.vn"
DEFAULT_DELAY_SECONDS = 2.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Danh mục tin tức & chính sách trọng yếu của VNBA
VNBA_CATEGORIES = {
    "gop-y-chinh-sach": "/vi/hashtag/gop-y-chinh-sach-2023-7840",
    "du-thao-luat": "/vi/hashtag/du-thao-luat-7841",
    "tin-nganh-ngan-hang": "/vi/hashtag/tin-nganh-ngan-hang-7828",
    "tin-tuc-chung": "/cms/index/latest-post",
}

DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:TT|NQ|NĐ|QĐ|CV|CT)-(?:NHNN|CP|TTg|BTP|BTC|VNBA))\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_vnba_date(text: str) -> dt.datetime:
    """Chuyển đổi chuỗi ngày thành datetime UTC."""
    match = DATE_PATTERN.search(text)
    if not match:
        return dt.datetime.now(dt.timezone.utc)
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    return dt.datetime(year, month, day, 8, 0, 0, tzinfo=dt.timezone.utc)


def fetch_vnba_page(url: str, session: requests.Session, max_retries: int = 2) -> str | None:
    """Tải nội dung trang web VNBA với cơ chế xử lý HTTP 429 backoff."""
    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait_time = 25 * (attempt + 1)
                logger.warning(f"VNBA HTTP 429 (Rate Limit) for {url}. Tạm nghỉ {wait_time}s trước khi thử lại...")
                time.sleep(wait_time)
                continue
            logger.warning(f"VNBA fetch HTTP {resp.status_code} for {url}")
            break
        except Exception as e:
            logger.warning(f"VNBA fetch error for {url}: {e}")
            break
    return None


def parse_vnba_listing(html: str) -> list[dict[str, str]]:
    """Trích xuất danh sách link bài viết từ trang chuyên mục."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if len(title) < 20:
            continue
        if href.endswith(".htm") and "/vi/" in href:
            full_url = urljoin(BASE_URL, href)
            if full_url not in seen:
                seen.add(full_url)
                articles.append({"title": title, "url": full_url})

    return articles


def parse_vnba_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách chi tiết bài viết chính sách ngân hàng theo 11 cột chuẩn."""
    soup = BeautifulSoup(html, "html.parser")

    # Headline
    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline:
        return None

    # Published date
    date_text = ""
    for el in soup.find_all(["span", "div", "p"]):
        t = el.get_text(strip=True)
        if any(w in t.lower() for w in ["thứ", "ngày", "202", "201"]):
            m = DATE_PATTERN.search(t)
            if m:
                date_text = t
                break
    published_at = parse_vnba_date(date_text)

    # Paragraphs / Body content
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
        "source": "vnba",
        "issuing_body": "Hiệp hội Ngân hàng Việt Nam (VNBA)",
        "doc_type": "BANKING_POLICY",
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
    """Lưu bài viết vào staging.macro_policy và core.macro_policy theo chuẩn 11 cột."""
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

    con.register("df_vnba_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vnba_staging")
    con.unregister("df_vnba_staging")

    con.register("df_vnba_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_vnba_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_vnba_core")
    return n_written


def load_existing_vnba_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL đã thu thập để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vnba'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_vnba_crawler(
    categories: list[str] | None = None,
    max_articles_per_cat: int = 8,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy quy trình cào VNBA với kiểm soát tốc độ và giới hạn số bài mỗi chuyên mục."""
    if categories is None:
        categories = list(VNBA_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_vnba_urls(con)

    total_discovered = 0
    total_written = 0

    for cat_name in categories:
        path = VNBA_CATEGORIES.get(cat_name, cat_name)
        cat_url = urljoin(BASE_URL, path)
        logger.info(f"=== Bắt đầu cào VNBA: {cat_name} ({cat_url}) ===")

        html = fetch_vnba_page(cat_url, session)
        if not html:
            continue

        articles = parse_vnba_listing(html)
        new_articles = [a for a in articles if a["url"] not in existing_urls][:max_articles_per_cat]
        total_discovered += len(articles)

        records = []
        for item in new_articles:
            time.sleep(delay_seconds)
            art_html = fetch_vnba_page(item["url"], session)
            if not art_html:
                continue
            rec = parse_vnba_article(art_html, item["url"], fallback_title=item["title"])
            if rec:
                records.append(rec)
                existing_urls.add(item["url"])

        if records:
            df = pd.DataFrame(records)
            n = write_macro_policy(con, df)
            total_written += n
            logger.info(f"[{cat_name}] Đã lưu +{n} bài viết chính sách ngân hàng mới.")

    con.close()
    return {
        "categories": categories,
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Hiệp hội Ngân hàng Việt Nam (VNBA) Policy Crawler")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="DuckDB database path")
    parser.add_argument("--max-articles", type=int, default=5, help="Số bài tối đa mỗi chuyên mục")
    args = parser.parse_args()

    summary = run_vnba_crawler(db_path=args.db, max_articles_per_cat=args.max_articles)
    print("\n=== VNBA Banking Crawler Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
