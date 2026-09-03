"""Báo Điện tử Chính phủ (baochinhphu.vn) Regulatory & Macro Policy Crawler.

Crawls official Vietnamese Government directives, Prime Minister decisions,
macroeconomic briefings, and regulatory resolutions from baochinhphu.vn.
Persists clean, structured policy records into `staging.macro_policy` and
`core.macro_policy` with deduplication on `source_url`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin
import urllib.robotparser

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)
BASE_URL = "https://baochinhphu.vn"
ROBOTS_URL = "https://baochinhphu.vn/robots.txt"
REQUEST_DELAY_SECONDS = 0.5

# Primary macro and regulatory categories on baochinhphu.vn
CATEGORY_SLUGS: dict[str, str] = {
    "chi-dao-dieu-hanh": "Chỉ đạo điều hành Chính phủ",
    "kinh-te": "Kinh tế vĩ mô",
    "kinh-te/ngan-hang": "Ngân hàng & Tài chính",
    "kinh-te/chung-khoan": "Thị trường Chứng khoán",
    "kinh-te/kinh-doanh": "Kinh doanh & Doanh nghiệp",
}

# Confirmed zone IDs for high-speed, deep historical pagination (/timelinelist/{zoneId}/{page}.htm)
CATEGORY_ZONE_IDS: dict[str, int] = {
    "chi-dao-dieu-hanh": 102263,
    "kinh-te": 1027,
    "kinh-te/ngan-hang": 102445,
    "kinh-te/chung-khoan": 1021064,
    "kinh-te/kinh-doanh": 1021126,
}

# Regex to detect official doc numbers like 33/NQ-CP, 15/CT-TTg, 60/2024/NĐ-CP
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|CT|TT|TB|CV)-(?:CP|TTg|NHNN|BCT|BTC|BXD|BKHĐT|HĐND|UBND))\b",
    re.IGNORECASE,
)


def check_robots_allowed(url: str, user_agent: str = USER_AGENT) -> bool:
    """Evaluates robots.txt compliance against baochinhphu.vn."""
    rp = urllib.robotparser.RobotFileParser()
    try:
        resp = requests.get(ROBOTS_URL, headers={"User-Agent": user_agent}, timeout=5)
        if resp.status_code in (404, 410):
            return True
        resp.raise_for_status()
        rp.parse(resp.text.splitlines())
        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logger.warning(f"Could not check robots.txt for {url}: {e} -- assuming allowed per verified file")
        return True


def extract_doc_metadata(headline: str, body_text: str = "") -> tuple[str, str | None, str]:
    """Extracts document type, official document number, and issuing body.

    Returns (doc_type, doc_number, issuing_body).
    """
    combined = headline + " " + (body_text[:1000] if body_text else "")

    num_match = DOC_NUMBER_PATTERN.search(combined)
    doc_number = num_match.group(1).upper() if num_match else None

    # Determine document type
    if re.search(r"\b(?i:Nghị\s+quyết)\b", headline) or (doc_number and "/NQ-" in doc_number):
        doc_type = "Nghị quyết"
    elif re.search(r"\b(?i:Nghị\s+định)\b", headline) or (doc_number and "/NĐ-" in doc_number):
        doc_type = "Nghị định"
    elif re.search(r"\b(?i:Quyết\s+định)\b", headline) or (doc_number and "/QĐ-" in doc_number):
        doc_type = "Quyết định"
    elif re.search(r"\b(?i:Chỉ\s+thị)\b", headline) or (doc_number and "/CT-" in doc_number):
        doc_type = "Chỉ thị"
    elif re.search(r"\b(?i:Thông\s+tư)\b", headline) or (doc_number and "/TT-" in doc_number):
        doc_type = "Thông tư"
    elif re.search(r"\b(?i:Họp\s+báo|Thông\s+cáo)\b", headline):
        doc_type = "Thông cáo báo chí"
    elif re.search(r"\b(?i:Chỉ\s+đạo|Điều\s+hành|Công\s+điện)\b", headline):
        doc_type = "Chỉ đạo điều hành"
    else:
        doc_type = "Chính sách vĩ mô"

    # Determine issuing body
    if doc_number and "-TTG" in doc_number:
        issuing_body = "Thủ tướng Chính phủ"
    elif doc_number and "-CP" in doc_number:
        issuing_body = "Chính phủ"
    elif doc_number and "-NHNN" in doc_number:
        issuing_body = "Ngân hàng Nhà nước Việt Nam"
    elif doc_number and "-BTC" in doc_number:
        issuing_body = "Bộ Tài chính"
    elif "Thủ tướng" in headline:
        issuing_body = "Thủ tướng Chính phủ"
    elif "Ngân hàng Nhà nước" in headline:
        issuing_body = "Ngân hàng Nhà nước Việt Nam"
    else:
        issuing_body = "Chính phủ"

    return doc_type, doc_number, issuing_body


def parse_article_links(html: str) -> list[dict[str, str]]:
    """Extracts candidate article links and titles from a category listing page."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)

        if not href.endswith(".htm") and not href.endswith(".html"):
            continue
        if len(title) < 15:
            continue
        if any(skip in href for skip in ["/video-", "/media-", "/anh-", "/chu-de/"]):
            continue

        abs_url = urljoin(BASE_URL, href)
        if abs_url in seen_urls:
            continue

        seen_urls.add(abs_url)
        articles.append({"url": abs_url, "title": title})

    return articles


def fetch_article_page(url: str) -> str:
    """Fetches full HTML for an article with politeness delay."""
    time.sleep(REQUEST_DELAY_SECONDS)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    return resp.text


def parse_article_record(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Parses article detail page for timestamp, title, and body text."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Headline
    h1 = soup.find("h1")
    og_title = soup.find("meta", property="og:title")
    headline = (h1.get_text(strip=True) if h1 else (og_title.get("content") if og_title else fallback_title)).strip()
    if not headline:
        return None

    # 2. Publication timestamp
    pub_meta = soup.find("meta", property="article:published_time")
    if pub_meta and pub_meta.get("content"):
        raw_time = pub_meta["content"].strip()
        try:
            published_at = dt.datetime.fromisoformat(raw_time)
        except Exception:
            published_at = dt.datetime.now(dt.timezone.utc)
    else:
        published_at = dt.datetime.now(dt.timezone.utc)

    # 3. Sapo / Summary
    sapo = soup.find("h2", class_="sapo") or soup.find("div", class_="sapo")
    summary = sapo.get_text(strip=True) if sapo else None

    # 4. Body
    detail = soup.find("div", class_="detail-content") or soup.find("div", id="content-body")
    body = detail.get_text(separator="\n", strip=True) if detail else None
    if not body or len(body) < 100:
        return None

    # 5. Document metadata
    doc_type, doc_number, issuing_body = extract_doc_metadata(headline, body)

    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "baochinhphu",
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


def write_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Idempotently writes macro policy records to staging and core tables."""
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
            raise ValueError(f"Missing required column '{col}' in macro_policy dataframe")

    # Staging write
    con.register("df_macro_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_macro_staging")
    con.unregister("df_macro_staging")

    # Core write with primary key idempotency (ON CONFLICT DO NOTHING)
    con.register("df_macro_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_macro_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_macro_core")

    return n_written


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Reads existing source_urls from core.macro_policy for deduplication."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def crawl_category(
    cat_slug: str,
    max_pages: int,
    con: duckdb.DuckDBPyConnection,
    existing_urls: set[str],
) -> dict[str, int]:
    """Crawls a single baochinhphu category up to max_pages."""
    total_discovered = 0
    total_written = 0
    consecutive_empty = 0
    zone_id = CATEGORY_ZONE_IDS.get(cat_slug)

    for page in range(1, max_pages + 1):
        if page == 1:
            cat_url = f"{BASE_URL}/{cat_slug}.htm"
        elif zone_id:
            cat_url = f"{BASE_URL}/timelinelist/{zone_id}/{page}.htm"
        else:
            cat_url = f"{BASE_URL}/{cat_slug}/trang-{page}.htm"

        logger.info(f"[{cat_slug}] Fetching page {page}/{max_pages}: {cat_url}")
        time.sleep(REQUEST_DELAY_SECONDS)

        try:
            resp = requests.get(cat_url, headers={"User-Agent": USER_AGENT}, timeout=15)
            if resp.status_code == 404:
                logger.info(f"[{cat_slug}] Page {page} returned 404. Reached end of category.")
                break
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning(f"[{cat_slug}] Failed to fetch page {page}: {e}")
            break

        articles = parse_article_links(html)
        if not articles:
            logger.info(f"[{cat_slug}] Page {page} returned 0 articles. Reached end of category.")
            break

        total_discovered += len(articles)

        new_articles = [a for a in articles if a["url"] not in existing_urls]
        if not new_articles:
            consecutive_empty += 1
            if consecutive_empty >= 5 and page >= 10:
                logger.info(f"[{cat_slug}] 5 consecutive pages with 0 new articles at page {page}. Stopping.")
                break
            continue
        else:
            consecutive_empty = 0

        records = []
        for art in new_articles:
            url = art["url"]
            try:
                art_html = fetch_article_page(url)
                rec = parse_article_record(art_html, url, fallback_title=art["title"])
                if rec:
                    records.append(rec)
                    existing_urls.add(url)
            except Exception as e:
                logger.warning(f"Failed to fetch/parse article {url}: {e}")

        if records:
            df_page = pd.DataFrame(records)
            n_written = write_macro_policy(con, df_page)
            total_written += n_written
            logger.info(
                f"[{cat_slug}] Page {page:2d}: {len(records)} parsed, +{n_written} written (Total: {total_written})"
            )

    return {"discovered": total_discovered, "written": total_written}


def run_baochinhphu_crawler(
    categories: list[str] | None = None,
    max_pages: int = 5,
    db_path: str = "db/vesta.duckdb",
) -> dict[str, Any]:
    """Main entry point to crawl official Government macro & regulatory dispatches."""
    if categories is None:
        categories = list(CATEGORY_SLUGS.keys())

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_urls(con)

    total_discovered = 0
    total_written = 0

    for cat in categories:
        logger.info(f"=== Starting Government Policy Crawl: {cat} (max_pages={max_pages}) ===")
        stats = crawl_category(cat, max_pages, con, existing_urls)
        total_discovered += stats["discovered"]
        total_written += stats["written"]
        logger.info(f"=== Category {cat} complete: {stats['written']} written ===")

    con.close()

    return {
        "categories": categories,
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Báo Chính phủ Macro & Regulatory Policy Crawler")
    parser.add_argument("--categories", nargs="+", default=list(CATEGORY_SLUGS.keys()), help="Category slugs")
    parser.add_argument("--max-pages", type=int, default=5, help="Max pages per category")
    parser.add_argument("--db", default="db/vesta.duckdb", help="DuckDB path")
    args = parser.parse_args()

    summary = run_baochinhphu_crawler(
        categories=args.categories,
        max_pages=args.max_pages,
        db_path=args.db,
    )
    print("\n=== Government Policy Crawl Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
