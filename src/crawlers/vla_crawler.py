"""Hiệp hội Doanh nghiệp Dịch vụ Logistics Việt Nam (VLA - vla.com.vn) Logistics & Freight Crawler.

File: src/crawlers/vla_crawler.py
Description:
    Thu thập các thông tin chuyên ngành logistics, giá cước vận tải biển container,
    phụ phí cảng biển, chuỗi cung ứng xuất nhập khẩu và các quy định pháp luật hàng hải từ VLA.
    Tác động trực tiếp lên các mã cổ phiếu logistics & vận tải biển:
    GMD, HAH, VOS, VSC, TMS, VNT, SGP, PHP.
    Tuân thủ RFC 9309 (scratch/robots/vla-robots.txt: Crawl-delay: 3).
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

BASE_URL = "https://vla.com.vn"
DEFAULT_DELAY_SECONDS = 3.0  # Strictly enforces Crawl-delay: 3 from vla-robots.txt
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

VLA_CATEGORIES = {
    "tin-chuyen-nganh": "https://vla.com.vn/chuyen-muc/tin-tuc/tin-nganh/",
    "thong-bao-hiep-hoi": "https://vla.com.vn/chuyen-muc/thong-bao/",
}

LOGISTICS_TICKERS = ["GMD", "HAH", "VOS", "VSC", "TMS", "VNT", "SGP", "PHP", "DXP"]

DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:QĐ|TT|NQ|NĐ|TB|CV)-(?:BGTVT|BCT|BTC|CP|TTg|VLA))\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_vla_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày công bố bài viết VLA."""
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


def parse_vla_listing(html: str) -> list[dict[str, str]]:
    """Trích xuất danh sách link bài viết chuyên mục logistics."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if len(title) < 25 or not href.startswith("https://vla.com.vn/"):
            continue
        if any(skip in href for skip in ["/chuyen-muc/", "/tag/", "/danh-ba-hoi-vien/", "/lien-he/", "/wp-content/"]):
            continue
        if href not in seen:
            seen.add(href)
            articles.append({"title": title, "url": href})

    return articles


def parse_vla_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết logistics theo chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1") or soup.find("h2", class_=lambda c: c and "entry-title" in c)
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 10:
        return None

    published_at = parse_vla_date(soup, html[:1000])

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
        "source": "vla",
        "issuing_body": "Hiệp hội Doanh nghiệp Dịch vụ Logistics Việt Nam (VLA)",
        "doc_type": "LOGISTICS_POLICY",
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

    con.register("df_vla_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vla_staging")
    con.unregister("df_vla_staging")

    con.register("df_vla_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_vla_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_vla_core")
    return n_written


def load_existing_vla_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL VLA đã có để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vla'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_vla_crawler(
    categories: list[str] | None = None,
    max_articles_per_cat: int = 5,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào thông tin logistics VLA tuân thủ Crawl-delay: 3."""
    if categories is None:
        categories = list(VLA_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_vla_urls(con)

    total_discovered = 0
    total_written = 0

    for cat_name in categories:
        cat_url = VLA_CATEGORIES.get(cat_name, cat_name)
        logger.info(f"=== Bắt đầu cào VLA (Logistics): {cat_name} ({cat_url}) ===")

        try:
            resp = session.get(cat_url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"VLA category {cat_name} HTTP {resp.status_code}")
                continue
            html = resp.text
        except Exception as e:
            logger.warning(f"VLA request error: {e}")
            continue

        articles = parse_vla_listing(html)
        new_articles = [a for a in articles if a["url"] not in existing_urls][:max_articles_per_cat]
        total_discovered += len(articles)

        records = []
        for item in new_articles:
            time.sleep(delay_seconds)  # Crawl-delay: 3
            try:
                art_resp = session.get(item["url"], timeout=15)
                if art_resp.status_code == 200:
                    rec = parse_vla_article(art_resp.text, item["url"], fallback_title=item["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(item["url"])
            except Exception as e:
                logger.warning(f"Error fetching {item['url']}: {e}")

        if records:
            df = pd.DataFrame(records)
            n = write_macro_policy(con, df)
            total_written += n
            logger.info(f"[{cat_name}] Đã lưu +{n} tin tức ngành logistics mới.")

    con.close()
    return {
        "categories": categories,
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Hiệp hội Logistics Việt Nam (VLA) Crawler")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="DuckDB database path")
    parser.add_argument("--max-articles", type=int, default=5, help="Số bài tối đa mỗi chuyên mục")
    args = parser.parse_args()

    summary = run_vla_crawler(db_path=args.db, max_articles_per_cat=args.max_articles)
    print("\n=== VLA Logistics Crawler Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
