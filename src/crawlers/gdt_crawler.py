"""Tổng cục Thuế (gdt.gov.vn) Tax Policy & Regulatory Crawler.

Parses official tax notices, circular implementations, corporate tax rulings,
and VAT/CIT announcements captured in HAR network files (scratch/har/gdt/tin-tuc.har)
and enriches full article text from gdt.gov.vn.
Persists structured records into `staging.macro_policy` and `core.macro_policy`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
import re
import ssl
import sys
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from bs4 import BeautifulSoup
import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Quant-Crawler/2.1)"
)
BASE_URL = "https://www.gdt.gov.vn"
HAR_PATH = Path("scratch/har/gdt/tin-tuc.har")
REQUEST_DELAY_SECONDS = 0.5


def _create_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def clean_html(raw_html: Optional[str]) -> str:
    """Extracts clean plain text from HTML fragment."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def parse_articles_from_har(har_file: Path) -> list[dict[str, Any]]:
    """Extracts article links and metadata from GDT HAR file."""
    if not har_file.exists():
        logger.warning(f"HAR file not found: {har_file}")
        return []

    with open(har_file, "r", encoding="utf-8", errors="ignore") as f:
        data = json.load(f)

    articles = []
    seen_urls = set()

    for entry in data.get("log", {}).get("entries", []):
        mime = entry.get("response", {}).get("content", {}).get("mimeType", "")
        if "html" in mime:
            text = entry.get("response", {}).get("content", {}).get("text", "")
            if len(text) < 1000:
                continue
            soup = BeautifulSoup(text, "html.parser")
            for a in soup.find_all("a"):
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if len(title) > 15 and ("wcm:path" in href or "wcm%3apath" in href or "portal" in href):
                    full_url = f"{BASE_URL}/wps/portal/{href}" if not href.startswith("http") else href
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        # Extract date hint if present in URL
                        date_match = re.search(r"/(\d{4})/thang\+?(\d{1,2})/", href)
                        pub_date = dt.datetime.now(dt.timezone.utc)
                        if date_match:
                            try:
                                y = int(date_match.group(1))
                                m = int(date_match.group(2))
                                pub_date = dt.datetime(y, m, 1, 8, 0, tzinfo=dt.timezone.utc)
                            except Exception:
                                pass

                        articles.append({
                            "title": title,
                            "url": full_url,
                            "published_at": pub_date,
                        })

    return articles


def fetch_gdt_article_body(url: str, ctx: Optional[ssl.SSLContext] = None) -> str:
    """Fetches article page and extracts body text."""
    if ctx is None:
        ctx = _create_ssl_context()

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            # Target GDT content containers
            content_div = (
                soup.find("div", class_="content")
                or soup.find("div", id="content")
                or soup.find("div", class_="detail-content")
                or soup.find("div", class_="wpthemeInner")
                or soup.find("body")
            )
            if content_div:
                return clean_html(str(content_div))
    except Exception as e:
        logger.warning(f"Error fetching GDT body for {url}: {e}")
    return ""


def write_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Writes macro policy records into staging and core idempotently."""
    if df.empty:
        return 0

    required_cols = [
        "source", "issuing_body", "doc_type", "doc_number",
        "published_at", "available_at", "headline", "summary",
        "body", "source_url", "fetched_at"
    ]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}'")

    # Staging write
    con.register("df_gdt_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_gdt_staging")
    con.unregister("df_gdt_staging")

    # Core write
    con.register("df_gdt_core", df[required_cols])
    con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_gdt_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    con.unregister("df_gdt_core")
    return len(df)


def run_crawl(
    har_path: Path = HAR_PATH,
    fetch_bodies: bool = True,
    db_path: Optional[str] = None,
) -> int:
    """Extracts and ingests GDT articles."""
    if db_path:
        con = db.connect(db_path)
    else:
        try:
            con = db.connect()
        except duckdb.IOException:
            logger.warning("db/vesta.duckdb locked, falling back to db/vesta_latest_backup.duckdb")
            con = db.connect("db/vesta_latest_backup.duckdb")

    articles = parse_articles_from_har(har_path)
    logger.info(f"Extracted {len(articles)} articles from GDT HAR.")

    ctx = _create_ssl_context()
    records = []
    now = dt.datetime.now(dt.timezone.utc)

    for item in articles:
        url = item["url"]
        title = item["title"]
        pub_at = item["published_at"]

        body = ""
        if fetch_bodies:
            time.sleep(REQUEST_DELAY_SECONDS)
            body = fetch_gdt_article_body(url, ctx=ctx)

        # Detect doc number if mentioned in title
        doc_num_match = re.search(r"(Nghị quyết số\s+[\w/-]+|Thông tư số\s+[\w/-]+|Công điện số\s+[\w/-]+|Công văn số\s+[\w/-]+)", title)
        doc_number = doc_num_match.group(1) if doc_num_match else None

        records.append({
            "source": "gdt",
            "issuing_body": "Tổng cục Thuế",
            "doc_type": "Thông báo & Chính sách Thuế",
            "doc_number": doc_number,
            "published_at": pub_at,
            "available_at": pub_at,
            "headline": title,
            "summary": title,
            "body": body if body else title,
            "source_url": url,
            "fetched_at": now,
        })

    df = pd.DataFrame(records)
    if not df.empty:
        inserted = write_macro_policy(con, df)
        logger.info(f"SUCCESS: Ingested {inserted} GDT records into core.macro_policy.")
        con.close()
        return inserted

    con.close()
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Tổng cục Thuế (gdt.gov.vn) HAR Ingester")
    parser.add_argument("--db", type=str, default=None, help="DuckDB path (default auto)")
    parser.add_argument("--har", type=str, default=str(HAR_PATH), help="Path to tin-tuc.har")
    parser.add_argument("--no-bodies", action="store_true", help="Skip live body scraping")
    args = parser.parse_args()

    count = run_crawl(
        har_path=Path(args.har),
        fetch_bodies=not args.no_bodies,
        db_path=args.db,
    )
    print(f"GDT Ingestion finished. Ingested: {count} records.")


if __name__ == "__main__":
    main()
