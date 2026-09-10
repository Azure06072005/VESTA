"""Bộ Tài chính (mof.gov.vn) Macro & Fiscal Policy Crawler.

Crawls official Vietnamese Ministry of Finance decrees, budget reports,
tax guidelines, financial policy decisions, and treasury announcements.
Reverse-engineered from network traffic HAR captures (RESTful JSON API:
/api/articlecategory and /api/article/reads).
Persists structured records into `staging.macro_policy` and `core.macro_policy`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path
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
BASE_URL = "https://www.mof.gov.vn"
API_READS_URL = "https://www.mof.gov.vn/api/article/reads"
API_DETAIL_URL = "https://www.mof.gov.vn/api/article/getbyslug"
REQUEST_DELAY_SECONDS = 0.5

# Comprehensive categories on mof.gov.vn
CATEGORIES: dict[str, str] = {
    "tin-tuc-su-kien-8": "f0d30405-0417-46a5-9dd0-fd1472428c57",
    "thoi-su": "63661983-10cb-458c-b835-76d8c1276450",
    "tai-chinh-trong-nuoc": "2fa020f0-83e7-4aa7-afa5-189687a4f1cb",
    "nghien-cuu-trao-doi-4": "25a336ea-06f2-4e37-a0ad-ff470a1ce941",
    "tin-chinh-sach-tai-chinh": "38ccd03f-ccaf-4e4d-9319-b90df2207feb",
    "hoat-dong-nganh-tai-chinh": "34c5a20a-5c6b-4012-89e7-65d718ea31dc",
    "thi-truong-tai-chinh": "9d96ccc0-1a88-4887-98e1-d11c3e2c956a",
    "tai-chinh-phap-luat": "85139ab2-de82-45ab-8de8-eda3004285fd",
    "chi-dao-dieu-hanh-1": "227618ab-3f56-4eed-8b8f-7589893fb863",
    "tai-chinh-quoc-te": "29fa2fdf-d806-4732-9058-08dd333794fb",
    "tieu-diem": "1b595c9b-e6e1-4e25-9fed-ed54e2761c23",
    "thong-cao-bao-chi-2": "5760ab6b-0e52-47e8-937e-62525c66a877",
    "tin-tai-chinh-dia-phuong": "992e3f93-abff-428c-952f-ffd1c1c3cc6d",
    "thong-bao-9": "c8defaa0-b89d-492e-843c-8cd774c6917c",
}



def _create_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_article_list(
    category_id: str,
    offset: int = 0,
    limit: int = 10,
    ctx: Optional[ssl.SSLContext] = None,
) -> dict[str, Any]:
    """Fetches paginated articles from MOF REST API."""
    if ctx is None:
        ctx = _create_ssl_context()

    url = f"{API_READS_URL}?offset={offset}&limit={limit}"
    payload = json.dumps({"categoryId": category_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/",
        },
    )
    with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_article_detail(
    slug: str,
    ctx: Optional[ssl.SSLContext] = None,
) -> Optional[dict[str, Any]]:
    """Fetches full article body and metadata by slug."""
    if ctx is None:
        ctx = _create_ssl_context()

    url = f"{API_DETAIL_URL}?slug={slug}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") and isinstance(data.get("data"), dict):
                return data["data"]
    except Exception as e:
        logger.warning(f"Error fetching MOF article detail for slug '{slug}': {e}")
    return None


def clean_html(raw_html: Optional[str]) -> str:
    """Extracts clean plain text from HTML fragment."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def parse_mof_article_to_record(item: dict[str, Any], detail: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Formats MOF API article into canonical macro_policy schema."""
    slug = item.get("slug") or ""
    source_url = f"{BASE_URL}/webcenter/portal/btcvn/pages_r/l/tin-bo-tai-chinh?dDocName={slug}" if slug else f"mof://{item.get('id')}"
    if detail and detail.get("sourceLink"):
        source_url = detail["sourceLink"]

    headline = item.get("title", "").strip()
    summary = item.get("description", "")
    if summary:
        summary = summary.strip()

    body = ""
    if detail and detail.get("articleContent"):
        body = clean_html(detail["articleContent"])
    elif item.get("articleContent"):
        body = clean_html(item["articleContent"])
    else:
        body = summary

    # Parse timestamps
    pub_str = item.get("publicationTime") or (detail.get("publicationTime") if detail else None)
    published_at = dt.datetime.now(dt.timezone.utc)
    if pub_str:
        try:
            # Format: 2026-08-25T04:08:45Z
            clean_str = pub_str.replace("Z", "+00:00")
            published_at = dt.datetime.fromisoformat(clean_str)
        except Exception:
            pass

    return {
        "source": "mof",
        "issuing_body": "Bộ Tài chính",
        "doc_type": "Tin tức & Chính sách Tài chính",
        "doc_number": None,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline,
        "summary": summary,
        "body": body,
        "source_url": source_url,
        "fetched_at": dt.datetime.now(dt.timezone.utc),
    }


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
    con.register("df_mof_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_mof_staging")
    con.unregister("df_mof_staging")

    # Core write
    con.register("df_mof_core", df[required_cols])
    con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_mof_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    con.unregister("df_mof_core")
    return len(df)


def extract_from_har_files(har_dir: Path) -> list[dict[str, Any]]:
    """Extracts already captured MOF responses from local .har files."""
    records = []
    har_files = list(har_dir.glob("*.har"))
    for h in har_files:
        try:
            with open(h, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            for e in data.get("log", {}).get("entries", []):
                url = e.get("request", {}).get("url", "")
                if "mof.gov.vn/api/article/reads" in url:
                    resp_text = e.get("response", {}).get("content", {}).get("text", "")
                    if resp_text:
                        parsed = json.loads(resp_text)
                        for item in parsed.get("data", []):
                            rec = parse_mof_article_to_record(item)
                            records.append(rec)
        except Exception as err:
            logger.warning(f"Error reading HAR {h}: {err}")
    return records


def run_crawl(
    max_pages: int = 5,
    page_size: int = 10,
    fetch_details: bool = True,
    har_only: bool = False,
    db_path: Optional[str] = None,
) -> int:
    """Main crawler execution."""
    if db_path:
        con = db.connect(db_path)
    else:
        try:
            con = db.connect()
        except duckdb.IOException:
            logger.warning("db/vesta.duckdb locked by IDE process, falling back to db/vesta_latest_backup.duckdb")
            con = db.connect("db/vesta_latest_backup.duckdb")
    ctx = _create_ssl_context()
    all_records = []

    # 1. Harvest from local HAR files first
    har_dir = Path("scratch/har/mof")
    if har_dir.exists():
        har_recs = extract_from_har_files(har_dir)
        logger.info(f"Extracted {len(har_recs)} articles from local MOF HAR files.")
        all_records.extend(har_recs)

    if not har_only:
        # 2. Crawl high-priority categories via live REST API
        for cat_name, cat_id in CATEGORIES.items():
            logger.info(f"Crawling MOF category: {cat_name} (ID: {cat_id})")
            for page in range(max_pages):
                offset = page * page_size
                try:
                    res = fetch_article_list(cat_id, offset=offset, limit=page_size, ctx=ctx)
                    items = res.get("data", [])
                    if not items:
                        break

                    for item in items:
                        slug = item.get("slug")
                        detail = None
                        if fetch_details and slug:
                            time.sleep(REQUEST_DELAY_SECONDS)
                            detail = fetch_article_detail(slug, ctx=ctx)
                        rec = parse_mof_article_to_record(item, detail)
                        all_records.append(rec)

                    logger.info(f"  Page {page + 1}/{max_pages}: fetched {len(items)} articles (Total available: {res.get('total')})")
                    time.sleep(REQUEST_DELAY_SECONDS)
                except Exception as e:
                    logger.warning(f"Error fetching page {page} for {cat_name}: {e}")
                    break

    # Deduplicate in memory on source_url
    unique_records = {r["source_url"]: r for r in all_records}.values()
    df = pd.DataFrame(list(unique_records))

    if not df.empty:
        inserted = write_macro_policy(con, df)
        logger.info(f"SUCCESS: Ingested {inserted} unique MOF records into core.macro_policy.")
        con.close()
        return inserted

    con.close()
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Bộ Tài chính (mof.gov.vn) Macro & Fiscal Policy Crawler")
    parser.add_argument("--db", type=str, default=None, help="DuckDB path (default auto)")
    parser.add_argument("--max-pages", type=int, default=5, help="Number of pages to crawl per category")
    parser.add_argument("--page-size", type=int, default=10, help="Articles per page")
    parser.add_argument("--har-only", action="store_true", help="Only extract from local HAR files without network requests")
    parser.add_argument("--no-details", action="store_true", help="Skip detail body fetches")
    args = parser.parse_args()

    count = run_crawl(
        max_pages=args.max_pages,
        page_size=args.page_size,
        fetch_details=not args.no_details,
        har_only=args.har_only,
        db_path=args.db,
    )
    print(f"MOF Crawler finished. Ingested: {count} records.")


if __name__ == "__main__":
    main()
