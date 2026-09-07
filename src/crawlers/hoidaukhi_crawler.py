"""Hội Dầu khí Việt Nam (VPA - hoidaukhi.vn) Oil & Gas Policy Crawler.

File: src/crawlers/hoidaukhi_crawler.py
Description:
    Thu thập các bài viết phản biện cơ chế chính sách, sửa đổi Luật Dầu khí,
    khung pháp lý LNG, tiến độ đại dự án Lô B - Ô Môn, các mỏ khí ngoài khơi
    và giá dầu quốc tế từ Hội Dầu khí Việt Nam.
    Tác động trực tiếp lên các mã cổ phiếu ngành dầu khí & năng lượng:
    GAS, PVD, PVS, BSR, PLX, PVT, PVC, PVB, PVO.
    Tuân thủ RFC 9309 (scratch/robots/hoidaukhi-robots.txt).
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

BASE_URL = "https://hoidaukhi.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

HDK_CATEGORIES = {
    "co-che-chinh-sach": "https://hoidaukhi.vn/chuyen-muc/tu-van-phan-bien/co-che-chinh-sach/",
    "khoa-hoc-cong-nghe": "https://hoidaukhi.vn/chuyen-muc/khoa-hoc-cong-nghe/",
}

OIL_GAS_TICKERS = ["GAS", "PVD", "PVS", "BSR", "PLX", "PVT", "PVC", "PVB", "PVO", "CNG"]

DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:QĐ|TT|NQ|NĐ|TB|CV)-(?:BCT|CP|TTg|BTC))\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_hdk_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày công bố bài viết Hội Dầu Khí."""
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        try:
            return dt.datetime.fromisoformat(time_tag["datetime"].replace("Z", "+00:00"))
        except Exception:
            pass

    m = DATE_PATTERN.search(text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return dt.datetime(year, month, day, 8, 0, 0, tzinfo=dt.timezone.utc)

    return dt.datetime.now(dt.timezone.utc)


def parse_hdk_listing(html: str) -> list[dict[str, str]]:
    """Trích xuất danh sách link bài viết chuyên mục dầu khí."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if len(title) < 25 or not href.startswith("https://hoidaukhi.vn/"):
            continue
        if any(skip in href for skip in ["/chuyen-muc/", "/tag/", "/gioi-thieu/", "/lien-he/", "/wp-content/"]):
            continue
        if href not in seen:
            seen.add(href)
            articles.append({"title": title, "url": href})

    return articles


def parse_hdk_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết dầu khí theo chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 10:
        return None

    published_at = parse_hdk_date(soup, html[:1000])

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
        "source": "hoidaukhi",
        "issuing_body": "Hội Dầu khí Việt Nam (VPA)",
        "doc_type": "ENERGY_POLICY",
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

    con.register("df_hdk_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_hdk_staging")
    con.unregister("df_hdk_staging")

    con.register("df_hdk_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_hdk_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_hdk_core")
    return n_written


def load_existing_hdk_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL Hội Dầu Khí đã có để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'hoidaukhi'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_hoidaukhi_crawler(
    categories: list[str] | None = None,
    max_articles_per_cat: int = 5,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào thông tin chính sách dầu khí."""
    if categories is None:
        categories = list(HDK_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_hdk_urls(con)

    total_discovered = 0
    total_written = 0

    for cat_name in categories:
        cat_url = HDK_CATEGORIES.get(cat_name, cat_name)
        logger.info(f"=== Bắt đầu cào Hội Dầu Khí: {cat_name} ({cat_url}) ===")

        try:
            resp = session.get(cat_url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"HDK category {cat_name} HTTP {resp.status_code}")
                continue
            html = resp.text
        except Exception as e:
            logger.warning(f"HDK request error: {e}")
            continue

        articles = parse_hdk_listing(html)
        new_articles = [a for a in articles if a["url"] not in existing_urls][:max_articles_per_cat]
        total_discovered += len(articles)

        records = []
        for item in new_articles:
            time.sleep(delay_seconds)
            try:
                art_resp = session.get(item["url"], timeout=15)
                if art_resp.status_code == 200:
                    rec = parse_hdk_article(art_resp.text, item["url"], fallback_title=item["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(item["url"])
            except Exception as e:
                logger.warning(f"Error fetching {item['url']}: {e}")

        if records:
            df = pd.DataFrame(records)
            n = write_macro_policy(con, df)
            total_written += n
            logger.info(f"[{cat_name}] Đã lưu +{n} tin tức ngành dầu khí mới.")

    con.close()
    return {
        "categories": categories,
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Hội Dầu khí Việt Nam (VPA) Crawler")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="DuckDB database path")
    parser.add_argument("--max-articles", type=int, default=5, help="Số bài tối đa mỗi chuyên mục")
    args = parser.parse_args()

    summary = run_hoidaukhi_crawler(db_path=args.db, max_articles_per_cat=args.max_articles)
    print("\n=== Hoi Dau khi Crawler Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
