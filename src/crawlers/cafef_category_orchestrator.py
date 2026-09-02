"""F004c Orchestrator: High-Throughput Streaming Category Crawler & Body Enrichment.

Crawls CafeF editorial categories, streams page by page, enriches article bodies
concurrently with polite delays, and persists clean records incrementally to DuckDB.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import logging
import re
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawlers.cafef_article_body import fetch_article_html, parse_article_body
from crawlers.cafef_category_news import (
    CATEGORY_IDS,
    fetch_category_landing_page,
    fetch_timeline_page,
    parse_article_links,
)
from etl import db

logger = logging.getLogger(__name__)

PREFIX_TICKER_PATTERN = re.compile(r"^([A-Z0-9]{3,4}):\s*")
SLUG_TICKER_PATTERN = re.compile(r"/([A-Z0-9]{3,4})-\d+(?:/|\.chn|$)")
WORD_TICKER_PATTERN = re.compile(r"\b([A-Z0-9]{3,4})\b")


def extract_symbol(title: str, url: str, valid_symbols: set[str]) -> str:
    """Extracts stock symbol from title or URL slug if present in valid_symbols universe.
    Falls back to 'VNINDEX' for broad market/macroeconomic editorial articles.
    """
    m_prefix = PREFIX_TICKER_PATTERN.match(title.strip())
    if m_prefix:
        sym = m_prefix.group(1).upper()
        if sym in valid_symbols:
            return sym

    m_slug = SLUG_TICKER_PATTERN.search(url)
    if m_slug:
        sym = m_slug.group(1).upper()
        if sym in valid_symbols:
            return sym

    for word in WORD_TICKER_PATTERN.findall(title):
        w = word.upper()
        if w in valid_symbols and len(w) >= 3:
            return w

    return "VNINDEX"


def load_valid_symbols(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Loads active symbols from core.dim_symbol and core.dim_symbol_cafef."""
    symbols: set[str] = set()
    try:
        rows = con.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
        symbols.update(r[0] for r in rows if r[0])
    except Exception as e:
        logger.warning(f"Could not read core.dim_symbol: {e}")

    try:
        rows = con.execute("SELECT DISTINCT symbol FROM core.dim_symbol_cafef").fetchall()
        symbols.update(r[0] for r in rows if r[0])
    except Exception:
        pass

    return symbols


def load_existing_source_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Reads all existing source_urls from core.news for zero-waste deduplication."""
    try:
        rows = con.execute("SELECT DISTINCT source_url FROM core.news WHERE source_url IS NOT NULL").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def enrich_article_record(
    article_link: dict[str, Any],
    valid_symbols: set[str],
) -> dict[str, Any] | None:
    """Fetches HTML and parses article body & timestamp for a single article link."""
    url = article_link["url"]

    try:
        html = fetch_article_html(url)
        parsed = parse_article_body(html, url)
    except Exception as e:
        logger.warning(f"Failed to fetch/parse body for {url}: {e}")
        return None

    headline = (article_link.get("title") or "").strip()
    if not headline and parsed.get("title"):
        headline = str(parsed["title"]).strip()

    published_at_str = parsed.get("published_at")
    if published_at_str:
        try:
            pub_dt = dt.datetime.fromisoformat(published_at_str)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pub_dt = dt.datetime.now(dt.timezone.utc)
    else:
        pub_dt = dt.datetime.now(dt.timezone.utc)

    body_text = parsed.get("body")
    symbol = extract_symbol(headline, url, valid_symbols)
    fetched_at = dt.datetime.now(dt.timezone.utc)

    return {
        "symbol": symbol,
        "source": "cafef",
        "published_at": pub_dt,
        "available_at": pub_dt,
        "headline": headline,
        "body": body_text,
        "source_url": url,
        "fetched_at": fetched_at,
    }


def write_category_news(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Inserts enriched category articles into core.news with source_url deduplication."""
    if df.empty:
        return 0

    con.register("df_incoming", df)
    row = con.execute("""
        SELECT COUNT(*) FROM df_incoming 
        WHERE source_url NOT IN (SELECT source_url FROM core.news)
    """).fetchone()
    to_insert_count = int(row[0]) if row else 0

    if to_insert_count == 0:
        return 0

    insert_sql = """
    INSERT INTO core.news (symbol, source, published_at, available_at, headline, body, source_url, fetched_at)
    SELECT symbol, source, published_at, available_at, headline, body, source_url, fetched_at
    FROM df_incoming
    WHERE source_url NOT IN (SELECT source_url FROM core.news)
    """
    con.execute(insert_sql)
    return to_insert_count


def crawl_category_streaming(
    cat: str,
    max_pages: int,
    con: duckdb.DuckDBPyConnection,
    valid_symbols: set[str],
    existing_urls: set[str],
    max_concurrency: int = 4,
) -> dict[str, int]:
    """Streams pages for a category, fetches bodies concurrently, and commits per page."""
    total_discovered = 0
    total_written = 0
    consecutive_empty = 0

    for p in range(1, max_pages + 1):
        try:
            if p == 1:
                html = fetch_category_landing_page(cat)
            else:
                html = fetch_timeline_page(cat, page=p)
            articles = parse_article_links(html)
        except Exception as e:
            logger.info(f"Category {cat}: page {p} hit terminal / error ({e}). Ending category.")
            break

        total_discovered += len(articles)
        new_articles = [a for a in articles if a["url"] not in existing_urls]

        if not new_articles:
            consecutive_empty += 1
            if consecutive_empty >= 5 and p >= 10:
                logger.info(f"Category {cat}: 5 consecutive pages with 0 new articles at page {p}. Stopping.")
                break
            continue
        else:
            consecutive_empty = 0

        # Concurrently fetch full article bodies for new articles
        enriched_records = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            futures = [executor.submit(enrich_article_record, art, valid_symbols) for art in new_articles]
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                if res:
                    enriched_records.append(res)
                    existing_urls.add(res["source_url"])

        if enriched_records:
            df_page = pd.DataFrame(enriched_records)
            n_written = write_category_news(con, df_page)
            total_written += n_written
            logger.info(
                f"[{cat}] Page {p:3d}/{max_pages}: {len(enriched_records)} enriched, "
                f"+{n_written} written (Cumulative: {total_written})"
            )

    return {"discovered": total_discovered, "written": total_written}


def run_category_orchestrator(
    categories: list[str] | None = None,
    max_pages: int = 50,
    db_path: str = "db/vesta.duckdb",
    max_concurrency: int = 4,
) -> dict[str, Any]:
    """Runs the streaming crawl & enrichment loop across requested categories."""
    if categories is None:
        categories = list(CATEGORY_IDS.keys())

    con = db.connect(db_path, read_only=False)
    valid_symbols = load_valid_symbols(con)
    existing_urls = load_existing_source_urls(con)

    total_discovered = 0
    total_written = 0

    for cat in categories:
        logger.info(f"=== Starting streaming crawl for category: {cat} (max_pages={max_pages}) ===")
        stats = crawl_category_streaming(
            cat=cat,
            max_pages=max_pages,
            con=con,
            valid_symbols=valid_symbols,
            existing_urls=existing_urls,
            max_concurrency=max_concurrency,
        )
        total_discovered += stats["discovered"]
        total_written += stats["written"]
        logger.info(f"=== Category {cat} finished: {stats['written']} written ===")

    con.close()

    summary = {
        "categories": categories,
        "total_discovered": total_discovered,
        "total_written": total_written,
    }
    logger.info(f"All categories crawl completed: {summary}")
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="CafeF Category News Crawler Orchestrator")
    parser.add_argument("--categories", nargs="+", default=list(CATEGORY_IDS.keys()), help="Categories to crawl")
    parser.add_argument("--max-pages", type=int, default=100, help="Max pages per category")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent workers for body parsing")
    parser.add_argument("--db", default="db/vesta.duckdb", help="DuckDB path")
    args = parser.parse_args()

    summary = run_category_orchestrator(
        categories=args.categories,
        max_pages=args.max_pages,
        db_path=args.db,
        max_concurrency=args.concurrency,
    )
    print("\n=== Crawl Orchestration Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
