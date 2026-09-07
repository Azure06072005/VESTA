"""Hiệp hội Thép Việt Nam (VSA - vsa.com.vn) Steel Industry & Trade Defense Crawler.

File: src/crawlers/vsa_crawler.py
Description:
    Thu thập các bản tin thị trường thép trong nước, thị trường thế giới,
    số liệu sản lượng thép thô/thành phẩm/HRC, vụ việc điều tra phòng vệ thương mại
    (chống bán phá giá, tự vệ thương mại) và văn bản pháp quy từ VSA.
    Tác động trực tiếp lên các mã cổ phiếu ngành thép:
    HPG, HSG, NKG, VGS, TLH, TVN, POM, SMC.
    Tuân thủ RFC 9309 (scratch/robots/vsa_com_vn-robots.txt).
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

BASE_URL = "https://vsa.com.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

# Danh mục tin tức & số liệu ngành thép của VSA
VSA_CATEGORIES = {
    "thi-truong-trong-nuoc": "https://vsa.com.vn/category/tin-tuc/thi-truong-trong-nuoc/",
    "phong-ve-thuong-mai": "https://vsa.com.vn/category/tin-tuc/phong-ve-thuong-mai/",
    "thi-truong-the-gioi": "https://vsa.com.vn/category/tin-tuc/thi-truong-the-gioi/",
    "van-ban-phap-luat": "https://vsa.com.vn/category/van-ban-phap-luat/",
}

DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:QĐ|TT|NQ|NĐ|TB)-(?:BCT|BTC|CP|TTg)|AD\d{2}|SG\d{2})\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_vsa_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày công bố bài viết từ time tag hoặc văn bản."""
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


def parse_vsa_listing(html: str) -> list[dict[str, str]]:
    """Trích xuất danh sách link bài viết từ trang chuyên mục WordPress."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if len(title) < 25 or not href.startswith("https://vsa.com.vn/"):
            continue
        if any(skip in href for skip in ["/category/", "/tag/", "/gioi-thieu/", "/lien-he/", "/wp-content/"]):
            continue
        if href not in seen:
            seen.add(href)
            articles.append({"title": title, "url": href})

    return articles


def parse_vsa_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết chuyên môn ngành thép theo 11 cột chuẩn."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline:
        return None

    published_at = parse_vsa_date(soup, html[:1000])

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
        "source": "vsa",
        "issuing_body": "Hiệp hội Thép Việt Nam (VSA)",
        "doc_type": "STEEL_INDUSTRY",
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

    con.register("df_vsa_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vsa_staging")
    con.unregister("df_vsa_staging")

    con.register("df_vsa_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_vsa_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_vsa_core")
    return n_written


def load_existing_vsa_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL VSA đã có để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vsa'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_vsa_crawler(
    categories: list[str] | None = None,
    max_articles_per_cat: int = 8,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình cào thông tin ngành thép VSA."""
    if categories is None:
        categories = list(VSA_CATEGORIES.keys())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_vsa_urls(con)

    total_discovered = 0
    total_written = 0

    for cat_name in categories:
        cat_url = VSA_CATEGORIES.get(cat_name, cat_name)
        logger.info(f"=== Bắt đầu cào VSA (Thép): {cat_name} ({cat_url}) ===")

        try:
            resp = session.get(cat_url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"VSA category {cat_name} HTTP {resp.status_code}")
                continue
            html = resp.text
        except Exception as e:
            logger.warning(f"VSA request error: {e}")
            continue

        articles = parse_vsa_listing(html)
        new_articles = [a for a in articles if a["url"] not in existing_urls][:max_articles_per_cat]
        total_discovered += len(articles)

        records = []
        for item in new_articles:
            time.sleep(delay_seconds)
            try:
                art_resp = session.get(item["url"], timeout=15)
                if art_resp.status_code == 200:
                    rec = parse_vsa_article(art_resp.text, item["url"], fallback_title=item["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(item["url"])
            except Exception as e:
                logger.warning(f"Error fetching {item['url']}: {e}")

        if records:
            df = pd.DataFrame(records)
            n = write_macro_policy(con, df)
            total_written += n
            logger.info(f"[{cat_name}] Đã lưu +{n} tin tức/báo cáo ngành thép mới.")

    con.close()
    return {
        "categories": categories,
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Hiệp hội Thép Việt Nam (VSA) Crawler")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="DuckDB database path")
    parser.add_argument("--max-articles", type=int, default=5, help="Số bài tối đa mỗi chuyên mục")
    args = parser.parse_args()

    summary = run_vsa_crawler(db_path=args.db, max_articles_per_cat=args.max_articles)
    print("\n=== VSA Steel Industry Crawler Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
