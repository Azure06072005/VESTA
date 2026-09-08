"""
Yahoo Finance Crawler (HAR-derived API)
Ingests breaking global macro, monetary policy, and market news into staging.macro_policy / core.macro_policy.
Extracted from finance.yahoo.com-News.har.
"""

import datetime as dt
import logging
import sys
import time
from typing import Any
import requests
from bs4 import BeautifulSoup
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yahoo_finance_crawler")

DB_PATH = "d:/VESTA/db/vesta_latest_backup.duckdb"

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://finance.yahoo.com",
    "referer": "https://finance.yahoo.com/markets/",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
}

ARTICLE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
}


def fetch_notifications(count: int = 200) -> list[dict[str, Any]]:
    """Fetches breaking market & macro notifications from Yahoo Finance feed."""
    url = f"https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count={count}&lang=en-US&region=US"
    logger.info(f"Đang tải {count} tin từ Yahoo Finance Activity Feed...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"Yahoo Activity Feed trả về status {resp.status_code}")
            return []
        data = resp.json()
        results = data.get("finance", {}).get("result", [])
        if not results:
            return []
        return results[0].get("notificationsWithMeta", [])
    except Exception as e:
        logger.error(f"Lỗi khi gọi Yahoo Activity Feed: {e}")
        return []


def fetch_search_news(queries: list[str]) -> list[dict[str, Any]]:
    """Fetches real-time topic news via Yahoo Finance search API."""
    all_news = []
    seen_links = set()
    for q in queries:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={q}&newsCount=25&listsCount=0&quotesCount=0"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                news_items = resp.json().get("news", [])
                logger.info(f"Search topic '{q}': tìm thấy {len(news_items)} bài viết.")
                for item in news_items:
                    link = item.get("link")
                    if link and link not in seen_links:
                        seen_links.add(link)
                        all_news.append(item)
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Lỗi khi search topic '{q}': {e}")
    return all_news


def extract_article_body(url: str) -> str:
    """Extracts article text from Yahoo Finance article webpage."""
    try:
        resp = requests.get(url, headers=ARTICLE_HEADERS, timeout=8)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        article_div = soup.find("article") or soup.find("div", class_="caas-body") or soup.find("div", class_="body")
        if article_div:
            paras = [p.get_text(strip=True) for p in article_div.find_all("p") if len(p.get_text(strip=True)) > 20]
            if paras:
                return "\n\n".join(paras)
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30]
        return "\n\n".join(paras) if paras else ""
    except Exception:
        return ""


def crawl_yahoo_finance(fetch_body: bool = True, max_body_fetch: int = 100) -> list[dict[str, Any]]:
    """Runs full crawl of Yahoo Finance using HAR-derived APIs."""
    now = dt.datetime.now(dt.timezone.utc)
    articles_map = {}

    # 1. Fetch notifications feed
    notifications = fetch_notifications(count=200)
    for n in notifications:
        url = n.get("articleUrl")
        title = n.get("notificationTitle") or n.get("title") or ""
        body_prev = n.get("body") or ""
        ts = n.get("publishTs")
        if not url or not title:
            continue
        
        pub_dt = dt.datetime.fromtimestamp(ts / 1000.0, dt.timezone.utc) if ts else now
        articles_map[url] = {
            "source": "yahoo_finance",
            "issuing_body": "Yahoo Finance / Global Macro",
            "doc_type": "news",
            "doc_number": n.get("id") or n.get("contentId"),
            "published_at": pub_dt,
            "available_at": pub_dt,
            "headline": title.strip(),
            "summary": body_prev.strip()[:1000] if body_prev else title.strip(),
            "body": body_prev.strip() if body_prev else title.strip(),
            "source_url": url.strip(),
            "fetched_at": now,
        }

    # 2. Fetch search topics
    macro_queries = ["Fed", "interest rates", "Vietnam", "tariffs", "oil", "inflation", "semiconductor"]
    search_news = fetch_search_news(macro_queries)
    for sn in search_news:
        url = sn.get("link")
        title = sn.get("title") or ""
        publisher = sn.get("publisher") or "Yahoo Finance"
        pub_ts = sn.get("providerPublishTime")
        if not url or not title:
            continue
        if url in articles_map:
            continue

        pub_dt = dt.datetime.fromtimestamp(pub_ts, dt.timezone.utc) if pub_ts else now
        articles_map[url] = {
            "source": "yahoo_finance",
            "issuing_body": f"Yahoo Finance / {publisher}",
            "doc_type": "news",
            "doc_number": sn.get("uuid"),
            "published_at": pub_dt,
            "available_at": pub_dt,
            "headline": title.strip(),
            "summary": title.strip(),
            "body": title.strip(),
            "source_url": url.strip(),
            "fetched_at": now,
        }

    records = list(articles_map.values())
    logger.info(f"Tổng hợp được {len(records)} bài viết từ Yahoo Finance.")

    # 3. Optional full-body enrichment
    if fetch_body and records:
        logger.info(f"Bắt đầu tải chi tiết bài viết (tối đa {max_body_fetch} bài)...")
        enriched = 0
        for r in records[:max_body_fetch]:
            full_body = extract_article_body(r["source_url"])
            if full_body and len(full_body) > len(r["body"]):
                r["body"] = full_body
                if not r["summary"] or r["summary"] == r["headline"]:
                    r["summary"] = full_body[:500]
                enriched += 1
            time.sleep(0.2)
        logger.info(f"Đã tải chi tiết thành công cho {enriched} bài viết.")

    return records


def ingest_to_duckdb(records: list[dict[str, Any]], db_path: str = DB_PATH) -> tuple[int, int]:
    """Ingests records into staging.macro_policy and core.macro_policy."""
    if not records:
        logger.info("Không có bản ghi nào để lưu.")
        return 0, 0

    import pandas as pd
    df = pd.DataFrame(records)
    required_cols = [
        "source", "issuing_body", "doc_type", "doc_number",
        "published_at", "available_at", "headline", "summary",
        "body", "source_url", "fetched_at"
    ]
    df = df[required_cols]

    conn = duckdb.connect(db_path, read_only=False)
    try:
        # 1. Insert into staging
        conn.register("df_staging", df)
        conn.execute("INSERT INTO staging.macro_policy SELECT * FROM df_staging")
        conn.unregister("df_staging")
        staging_inserted = len(df)

        # 2. Promote into core with deduplication
        before_count = conn.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()[0]
        conn.register("df_core", df)
        conn.execute("""
            INSERT INTO core.macro_policy
            SELECT * FROM df_core
            ON CONFLICT (source_url) DO UPDATE SET
                headline = EXCLUDED.headline,
                summary = EXCLUDED.summary,
                body = EXCLUDED.body,
                fetched_at = EXCLUDED.fetched_at
        """)
        conn.unregister("df_core")
        after_count = conn.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()[0]
        core_inserted = after_count - before_count

        logger.info(f"Đã nạp {staging_inserted} bản ghi vào staging.macro_policy.")
        logger.info(f"Số bản ghi mới thêm vào core.macro_policy: {core_inserted} (Tổng hiện tại: {after_count}).")
        return staging_inserted, core_inserted
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("=== BẮT ĐẦU CÀO TIN YAHOO FINANCE (HAR API) ===")
    recs = crawl_yahoo_finance(fetch_body=True, max_body_fetch=50)
    stg_cnt, core_new = ingest_to_duckdb(recs)
    logger.info(f"Hoàn thành! Staging: {stg_cnt}, Core mới: {core_new}")
