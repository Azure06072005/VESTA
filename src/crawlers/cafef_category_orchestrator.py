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
from crawlers.cafef_news import VN30_SYMBOLS
from etl import db

logger = logging.getLogger(__name__)

# Nhóm các chuyên mục Vĩ mô & Toàn cầu: Bắt buộc cào toàn bộ bao gồm cả thân bài (body content)
GLOBAL_ECONOMY_CATEGORIES = {
    "tai-chinh-quoc-te",
    "vi-mo-dau-tu",
    "kinh-te-so",
}

# Scoped (?i:...) applies case-insensitivity ONLY to the Vietnamese keywords.
# ([A-Z0-9]{3,4}) is strictly uppercase ASCII.
# SAFE_BUFFER_WORDS allows 1-2 common Vietnamese bridging words without risking false positives.
SAFE_BUFFER_WORDS = r"(?:của|hãng|nhóm|cp|tập\s+đoàn|ngân\s+hàng)"
CO_PHIEU_PATTERN = re.compile(rf"\b(?i:cổ\s+phiếu)(?:\s+{SAFE_BUFFER_WORDS})?\s+([A-Z0-9]{{3,4}})\b")
MA_CHUNG_KHOAN_PATTERN = re.compile(rf"\b(?i:mã\s+(?:chứng\s+khoán|CK))(?:\s+{SAFE_BUFFER_WORDS})?\s+([A-Z0-9]{{3,4}})\b")
PARENTHESIS_MA_PATTERN = re.compile(r"\((?i:mã(?:\s+CK)?|CK):\s*([A-Z0-9]{3,4})\)")
SLUG_TICKER_PATTERN = re.compile(r"^https?://cafef\.vn/([A-Z0-9]{3,4})-\d+/")

# Known collisions with major foreign tickers/entities
FOREIGN_TICKER_COLLISIONS = {"AMD", "CAT", "FOX", "AMP"}

# Context words proving domestic equity context for colliding tickers
DOMESTIC_CORROBORATING_KEYWORDS = (
    "flc", "cà mau", "thủy sản", "fpt telecom", "viễn thông", "armephaco", "dược",
    "hose", "hnx", "upcom", "niêm yết", "ctcp", "hđqt", "công ty cp", "chứng khoán",
)


def extract_symbol(
    title: str,
    url: str,
    valid_symbols: set[str],
    category_slug: str | None = None,
) -> str | None:
    """Extracts a Vietnamese stock symbol from title or URL slug with strict syntactic matching.
    Returns None if no unambiguous match is found (fail-closed, no silent fallbacks).
    """
    # Safeguard A: tai-chinh-quoc-te never contains domestic equity sentiment
    if category_slug == "tai-chinh-quoc-te":
        return None

    candidate: str | None = None

    # 1. Per-symbol URL landing slug check
    m_slug = SLUG_TICKER_PATTERN.search(url)
    if m_slug:
        candidate = m_slug.group(1)

    # 2. Syntactic headline patterns
    if not candidate:
        for pat in (CO_PHIEU_PATTERN, MA_CHUNG_KHOAN_PATTERN, PARENTHESIS_MA_PATTERN):
            m = pat.search(title)
            if m:
                candidate = m.group(1)
                break

    if not candidate:
        return None

    # Enforce uppercase ASCII and valid listed universe (core.dim_symbol)
    if not (candidate.isupper() and candidate in valid_symbols):
        return None

    # Safeguard B: Disambiguate foreign ticker collisions
    if candidate in FOREIGN_TICKER_COLLISIONS:
        title_lower = title.lower()
        if not any(kw in title_lower for kw in DOMESTIC_CORROBORATING_KEYWORDS):
            return None  # Fail closed: treat as foreign or ambiguous

    return candidate


def load_valid_symbols(con: duckdb.DuckDBPyConnection | None = None) -> set[str]:
    """Loads listed stock symbols exclusively from core.dim_symbol (HOSE, HNX, UPCOM).
    Excludes OTC/fund/unclassified entities from dim_symbol_cafef.
    """
    try:
        if con is not None:
            rows = con.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
            return {r[0] for r in rows if r[0]}
    except Exception:
        pass
    try:
        con_snap = db.connect(read_only=True)
        rows = con_snap.execute("SELECT DISTINCT symbol FROM core.dim_symbol").fetchall()
        con_snap.close()
        return {r[0] for r in rows if r[0]}
    except Exception as e:
        logger.warning(f"Could not read core.dim_symbol: {e}")
        return set()


def load_existing_source_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Reads all existing source_urls from core.news and core.news_resources for zero-waste deduplication."""
    existing = set()
    try:
        rows = con.execute("SELECT DISTINCT source_url FROM core.news WHERE source_url IS NOT NULL").fetchall()
        existing.update(r[0] for r in rows if r[0])
    except Exception:
        pass
    try:
        rows = con.execute("SELECT DISTINCT source_url FROM core.news_resources WHERE source_url IS NOT NULL").fetchall()
        existing.update(r[0] for r in rows if r[0])
    except Exception:
        pass
    return existing


def enrich_article_record(
    article_link: dict[str, Any],
    valid_symbols: set[str],
    category_slug: str | None = None,
) -> dict[str, Any] | None:
    """Xử lý bài viết chuyên mục theo chính sách phân cấp:
    1. Chuyên mục Global & Economy (tai-chinh-quoc-te, vi-mo-dau-tu, kinh-te-so):
       -> Bắt buộc cào toàn bộ nội dung bao gồm cả thân bài (body content).
       -> Nếu bài viết có mã CK: ghi vào core.news.
       -> Nếu là vĩ mô chung: ghi vào core.news_resources.
    2. Các chuyên mục khác (thi-truong-chung-khoan, bat-dong-san, doanh-nghiep...):
       -> Nếu là mã thuộc rổ VN30 (2023 - 2026): cào thân bài (body content).
       -> Các mã khác ngoài VN30: chỉ lưu headline (body = None, headline only).
    """
    url = article_link["url"]
    headline = (article_link.get("title") or "").strip()
    is_global_or_economy = category_slug in GLOBAL_ECONOMY_CATEGORIES

    symbol = extract_symbol(headline, url, valid_symbols, category_slug=category_slug)
    
    # Đối với các category thông thường: Bỏ qua nếu không có mã cổ phiếu
    if not is_global_or_economy and not symbol:
        return None

    # Xác định có cần cào body hay không
    need_body = False
    if is_global_or_economy:
        need_body = True
    elif symbol and (symbol in VN30_SYMBOLS):
        need_body = True

    parsed = {}
    body_text = None
    pub_dt = dt.datetime.now(dt.timezone.utc)

    if need_body:
        try:
            html = fetch_article_html(url)
            parsed = parse_article_body(html, url)
            body_text = parsed.get("body")
            
            published_at_str = parsed.get("published_at")
            if published_at_str:
                try:
                    pub_dt = dt.datetime.fromisoformat(published_at_str)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=dt.timezone.utc)
                except Exception:
                    pub_dt = dt.datetime.now(dt.timezone.utc)
            
            # Đối với VN30 ngoài dải 2023 - 2026: không lưu body
            if not is_global_or_economy and symbol and (pub_dt.year < 2023 or pub_dt.year > 2026):
                body_text = None
        except Exception as e:
            logger.debug(f"Không thể cào body cho {url}: {e}")
            body_text = None
    else:
        # Headline only: không tải mạng chi tiết
        body_text = None

    if not headline and parsed.get("title"):
        headline = str(parsed["title"]).strip()
        if not symbol:
            symbol = extract_symbol(headline, url, valid_symbols, category_slug=category_slug)

    fetched_at = dt.datetime.now(dt.timezone.utc)

    # Phân loại đích lưu trữ: core.news vs core.news_resources
    if symbol:
        return {
            "target_table": "core.news",
            "symbol": symbol,
            "source": "cafef",
            "published_at": pub_dt,
            "available_at": pub_dt,
            "headline": headline,
            "body": body_text,
            "source_url": url,
            "fetched_at": fetched_at,
        }
    elif is_global_or_economy:
        issuing = "CafeF Quốc tế" if category_slug == "tai-chinh-quoc-te" else "CafeF Vĩ mô"
        return {
            "target_table": "core.news_resources",
            "source": "cafef",
            "issuing_body": issuing,
            "doc_type": "Chuyên đề",
            "doc_number": None,
            "published_at": pub_dt,
            "available_at": pub_dt,
            "headline": headline,
            "summary": headline,
            "body": body_text,
            "source_url": url,
            "fetched_at": fetched_at,
        }
    return None


def write_category_news(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Inserts enriched category articles into core.news and core.news_resources."""
    if df.empty:
        return 0

    df_clean = df.drop_duplicates(subset=["source_url"]).copy()
    if "target_table" not in df_clean.columns:
        df_clean["target_table"] = "core.news"

    total_inserted = 0

    # 1. Ghi bài viết theo mã vào core.news
    df_news = df_clean[df_clean["target_table"] == "core.news"].copy()
    if not df_news.empty:
        news_cols = ["symbol", "source", "published_at", "available_at", "headline", "body", "source_url", "fetched_at"]
        df_news_data = df_news[news_cols]
        con.register("df_news_incoming", df_news_data)
        row = con.execute("""
            SELECT COUNT(*) FROM df_news_incoming 
            WHERE source_url NOT IN (SELECT source_url FROM core.news)
        """).fetchone()
        to_insert_news = int(row[0]) if row else 0

        if to_insert_news > 0:
            con.execute("""
                INSERT OR IGNORE INTO core.news (symbol, source, published_at, available_at, headline, body, source_url, fetched_at)
                SELECT symbol, source, published_at, available_at, headline, body, source_url, fetched_at
                FROM df_news_incoming
                WHERE source_url NOT IN (SELECT source_url FROM core.news)
            """)
            total_inserted += to_insert_news
        con.unregister("df_news_incoming")

    # 2. Ghi bài viết vĩ mô toàn cầu vào core.news_resources
    df_res = df_clean[df_clean["target_table"] == "core.news_resources"].copy()
    if not df_res.empty:
        res_cols = ["source", "issuing_body", "doc_type", "doc_number", "published_at", "available_at", "headline", "summary", "body", "source_url", "fetched_at"]
        df_res_data = df_res[res_cols]
        con.register("df_res_incoming", df_res_data)
        row = con.execute("""
            SELECT COUNT(*) FROM df_res_incoming 
            WHERE source_url NOT IN (SELECT source_url FROM core.news_resources)
        """).fetchone()
        to_insert_res = int(row[0]) if row else 0

        if to_insert_res > 0:
            con.execute("""
                INSERT OR IGNORE INTO core.news_resources (source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at)
                SELECT source, issuing_body, doc_type, doc_number, published_at, available_at, headline, summary, body, source_url, fetched_at
                FROM df_res_incoming
                WHERE source_url NOT IN (SELECT source_url FROM core.news_resources)
            """)
            total_inserted += to_insert_res
        con.unregister("df_res_incoming")

    return total_inserted


def crawl_category_streaming(
    cat: str,
    max_pages: int,
    con: duckdb.DuckDBPyConnection,
    valid_symbols: set[str],
    existing_urls: set[str],
    max_concurrency: int = 4,
) -> dict[str, int]:
    """Streams pages for a category, fetches bodies concurrently, and commits per page."""
    import time
    total_discovered = 0
    total_written = 0
    consecutive_empty = 0

    for p in range(1, max_pages + 1):
        html = None
        for attempt in range(3):
            try:
                if p == 1:
                    html = fetch_category_landing_page(cat)
                else:
                    html = fetch_timeline_page(cat, page=p)
                break
            except Exception as e:
                if attempt == 2:
                    logger.info(f"Category {cat}: page {p} failed after 3 attempts ({e}). Ending category.")
                    break
                time.sleep(1.0 * (attempt + 1))

        if html is None:
            break

        try:
            articles = parse_article_links(html)
        except Exception as e:
            logger.info(f"Category {cat}: page {p} returned no parsable articles ({e}). Ending category.")
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
            futures = [executor.submit(enrich_article_record, art, valid_symbols, cat) for art in new_articles]
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
    db_path: str = "db/vesta_news.duckdb",
    max_concurrency: int = 1,
) -> dict[str, Any]:
    """Runs the streaming crawl & enrichment loop across requested categories."""
    if categories is None:
        categories = list(CATEGORY_IDS.keys())

    if "vesta_news" in db_path:
        con = db.connect_news(read_only=False)
    else:
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
    parser.add_argument("--max-pages", type=int, default=50, help="Max pages per category")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent workers for body parsing")
    parser.add_argument("--db", default="db/vesta_news.duckdb", help="DuckDB path")
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
