"""
Yahoo Finance All-Dates Deep Crawler
Multi-stream historical crawler leveraging:
1. Nexus Gateway GraphQL GetFinanceTopicStream (16 core editorial topics with pagination)
2. Nexus Gateway GraphQL GetQSPLeafNewsStream (Global indices & commodity streams)
3. Activity Feed Breaking Notifications API (194 curated items)
4. Macro Topic Search News API (Fed, interest rates, Vietnam, tariffs, oil, semiconductors)
Stores deduplicated records directly into staging.macro_policy and core.macro_policy in vesta_latest_backup.duckdb.
"""

import datetime as dt
import logging
from pathlib import Path
import sys
import time
from typing import Any
import duckdb
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yahoo_all_dates_crawler")

DB_PATH = "d:/VESTA/db/vesta_latest_backup.duckdb"
GRAPHQL_URL = "https://nexus-gateway-prod.media.yahoo.com/"

CURRENT_DIR = Path(__file__).resolve().parent
with open(CURRENT_DIR / "get_finance_topic_stream.graphql", "r", encoding="utf-8") as f:
    TOPIC_QUERY = f.read()

with open(CURRENT_DIR / "get_qsp_leaf_news_stream.graphql", "r", encoding="utf-8") as f:
    LEAF_QUERY = f.read()

GRAPHQL_HEADERS = {
    "accept": "application/graphql-response+json, application/graphql+json, application/json",
    "content-type": "application/json",
    "origin": "https://finance.yahoo.com",
    "referer": "https://finance.yahoo.com/markets/",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Microsoft Edge";v="151", "Chromium";v="151"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
    "x-yahoo-cg-client-name": "finance",
    "x-yahoo-cg-client-version": "0.1.14418.1788543794",
    "y-rid": "6bbjmtll9tl5q"
}

API_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://finance.yahoo.com",
    "referer": "https://finance.yahoo.com/markets/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
}

CORE_TOPICS = [
    ("stock-market-news", "db1d46e0-a969-11e9-bff5-6dfdb80d79cf"),
    ("economic-news", "7ce2bfb8-c363-4498-930b-b6d86ae4dccf"),
    ("latest-news", "530aec16-61ed-4c8e-8fd8-f60d01bd0722"),
    ("tech", "dffbd430-02a2-11e7-bcfc-437e9432ca73"),
    ("earnings", "04d9350a-bbd1-4787-95be-740cc5ee8852"),
    ("artificial-intelligence", "b9b66d9c-c3ac-473a-98f2-59a2ab749b60"),
    ("crypto", "b1f0c990-db7a-11e7-a937-0d92c86f9da1"),
    ("housing-market", "aff2792f-3630-433b-9d0b-0692f91e2a92"),
    ("morning-brief", "32ef1e10-a174-11e8-b72b-b7a58875a002"),
    ("personal-finance-news", "a6d5f39c-4f21-4ab5-9955-7904052ef9f2"),
    ("yahoo-finance-originals", "0897608a-7d79-47df-9377-b07bd22b0fde"),
    ("etf-report", "bceaa821-70d6-4c98-9e31-e66829753cdc"),
    ("auto-industry", "1e3ae50f-72a9-44d0-b268-ec853c0ff565"),
    ("businesswire", "61f79c40-2f61-11e7-aaf7-a51cd0c0a187"),
    ("globenewswire", "1672c410-2f62-11e7-afbf-051c42d40139"),
    ("access-newswire", "0d1e0b30-2f63-11e7-bfdf-d5f9f2868b1a"),
]

MACRO_TICKERS = [
    "^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX", "CL=F", "GC=F", "DX-Y.NYB",
    "USDVND=X", "VNM", "NVDA", "AAPL", "MSFT", "GOOG", "TSLA"
]


def crawl_all_dates_yahoo(max_pages_per_topic: int = 5) -> list[dict[str, Any]]:
    """Crawls multi-stream Yahoo news spanning all available dates."""
    now = dt.datetime.now(dt.timezone.utc)
    articles_map = {}

    # 1. Nexus Gateway: Editorial Topics with Pagination
    logger.info("=== 1. Nexus Gateway: Quét các chuyên mục biên tập (Topic Streams) ===")
    for tname, tuuid in CORE_TOPICS:
        logger.info(f"-> Quét topic: {tname}...")
        for page in range(max_pages_per_topic):
            start = page * 25
            payload = {
                "operationName": "GetFinanceTopicStream",
                "query": TOPIC_QUERY,
                "variables": {
                    "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
                    "count": 25,
                    "start": start,
                    "listInput": {"uuid": tuuid},
                    "imageResize": []
                }
            }
            try:
                resp = requests.post(GRAPHQL_URL, headers=GRAPHQL_HEADERS, json=payload, timeout=10)
                if resp.status_code != 200:
                    break
                stream = resp.json().get("data", {}).get("lightyearList", {}).get("main", {}).get("stream", [])
                if not stream:
                    break
                for item in stream:
                    asset = item.get("asset", {})
                    aid = asset.get("id")
                    title = asset.get("title")
                    attrs = asset.get("contentAttributes", {})
                    url = attrs.get("canonicalUrl") or attrs.get("clickthroughUrl")
                    pub_str = attrs.get("pubDate")
                    provider = (attrs.get("provider") or {}).get("displayName") or "Yahoo Finance"
                    summary = attrs.get("summary") or title

                    if not url or not title or url in articles_map:
                        continue

                    try:
                        pub_dt = pd.to_datetime(pub_str, utc=True).to_pydatetime() if pub_str else now
                    except Exception:
                        pub_dt = now

                    articles_map[url] = {
                        "source": "yahoo_finance",
                        "issuing_body": f"Yahoo Finance / {provider}",
                        "doc_type": "news",
                        "doc_number": aid,
                        "published_at": pub_dt,
                        "available_at": pub_dt,
                        "headline": title.strip(),
                        "summary": summary.strip()[:1000] if summary else title.strip(),
                        "body": summary.strip() if summary else title.strip(),
                        "source_url": url.strip(),
                        "fetched_at": now,
                    }
                time.sleep(0.15)
            except Exception as e:
                logger.warning(f"Lỗi topic {tname} page {page}: {e}")
                break

    logger.info(f"Thu thập được {len(articles_map)} bài viết sau Topic Streams.")

    # 2. Nexus Gateway: Global Indices & Macro Tickers News
    logger.info("=== 2. Nexus Gateway: Quét tin theo chỉ số vĩ mô & hàng hóa ===")
    for page in range(max_pages_per_topic):
        start = page * 25
        payload = {
            "operationName": "GetQSPLeafNewsStream",
            "query": LEAF_QUERY,
            "variables": {
                "clientContext": {"device": "desktop", "lang": "en-US", "region": "US", "site": "finance"},
                "count": 25,
                "start": start,
                "listInput": {
                    "assetTypes": ["story", "video"],
                    "disableDedupe": False,
                    "enableBlockedContent": False,
                    "filterClientContext": False,
                    "queryVariables": {"tickerSymbol": MACRO_TICKERS},
                    "slug": "list=finance-US-en-US-ticker-all"
                },
                "imageResize": []
            }
        }
        try:
            resp = requests.post(GRAPHQL_URL, headers=GRAPHQL_HEADERS, json=payload, timeout=10)
            if resp.status_code != 200:
                break
            stream = resp.json().get("data", {}).get("lightyearList", {}).get("main", {}).get("stream", [])
            if not stream:
                break
            for item in stream:
                asset = item.get("asset", {})
                aid = asset.get("id")
                title = asset.get("title")
                attrs = asset.get("contentAttributes", {})
                url = attrs.get("canonicalUrl") or attrs.get("clickthroughUrl")
                pub_str = attrs.get("pubDate")
                provider = (attrs.get("provider") or {}).get("displayName") or "Yahoo Finance"
                summary = attrs.get("summary") or title

                if not url or not title or url in articles_map:
                    continue

                try:
                    pub_dt = pd.to_datetime(pub_str, utc=True).to_pydatetime() if pub_str else now
                except Exception:
                    pub_dt = now

                articles_map[url] = {
                    "source": "yahoo_finance",
                    "issuing_body": f"Yahoo Finance / {provider}",
                    "doc_type": "news",
                    "doc_number": aid,
                    "published_at": pub_dt,
                    "available_at": pub_dt,
                    "headline": title.strip(),
                    "summary": summary.strip()[:1000] if summary else title.strip(),
                    "body": summary.strip() if summary else title.strip(),
                    "source_url": url.strip(),
                    "fetched_at": now,
                }
            time.sleep(0.15)
        except Exception as e:
            logger.warning(f"Lỗi QSP Leaf Stream page {page}: {e}")
            break

    logger.info(f"Thu thập được {len(articles_map)} bài viết sau Macro Tickers.")

    # 3. Breaking Notifications Activity Feed (200 items)
    logger.info("=== 3. Activity Feed: Quét thông báo nóng ===")
    try:
        url_feed = "https://query1.finance.yahoo.com/ws/activity-feed/v1/notifications?count=200&lang=en-US&region=US"
        resp = requests.get(url_feed, headers=API_HEADERS, timeout=12)
        if resp.status_code == 200:
            notifs = resp.json().get("finance", {}).get("result", [{}])[0].get("notificationsWithMeta", [])
            for n in notifs:
                url = n.get("articleUrl")
                title = n.get("notificationTitle") or n.get("title") or ""
                body_prev = n.get("body") or ""
                ts = n.get("publishTs")
                if not url or not title or url in articles_map:
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
    except Exception as e:
        logger.warning(f"Lỗi Activity Feed: {e}")

    # 4. Search Topic News
    logger.info("=== 4. Search News: Quét từ khóa vĩ mô cốt lõi ===")
    search_queries = ["Fed", "interest rates", "Vietnam", "tariffs", "oil", "inflation", "semiconductor", "dollar index"]
    for q in search_queries:
        try:
            url_search = f"https://query1.finance.yahoo.com/v1/finance/search?q={q}&newsCount=25&listsCount=0&quotesCount=0"
            resp = requests.get(url_search, headers=API_HEADERS, timeout=10)
            if resp.status_code == 200:
                news_items = resp.json().get("news", [])
                for item in news_items:
                    url = item.get("link")
                    title = item.get("title")
                    publisher = item.get("publisher") or "Yahoo Finance"
                    pub_ts = item.get("providerPublishTime")
                    if not url or not title or url in articles_map:
                        continue

                    pub_dt = dt.datetime.fromtimestamp(pub_ts, dt.timezone.utc) if pub_ts else now
                    articles_map[url] = {
                        "source": "yahoo_finance",
                        "issuing_body": f"Yahoo Finance / {publisher}",
                        "doc_type": "news",
                        "doc_number": item.get("uuid"),
                        "published_at": pub_dt,
                        "available_at": pub_dt,
                        "headline": title.strip(),
                        "summary": title.strip(),
                        "body": title.strip(),
                        "source_url": url.strip(),
                        "fetched_at": now,
                    }
            time.sleep(0.15)
        except Exception as e:
            logger.warning(f"Lỗi search topic {q}: {e}")

    records = list(articles_map.values())
    logger.info(f"TỔNG KẾT: Thu thập thành công {len(records)} bài viết Yahoo Finance không trùng lặp.")
    return records


def ingest_to_duckdb(records: list[dict[str, Any]], db_path: str = DB_PATH) -> tuple[int, int]:
    """Ingests records into staging and core.macro_policy."""
    if not records:
        logger.info("Không có bản ghi nào để lưu.")
        return 0, 0

    df = pd.DataFrame(records)
    required_cols = [
        "source", "issuing_body", "doc_type", "doc_number",
        "published_at", "available_at", "headline", "summary",
        "body", "source_url", "fetched_at"
    ]
    df = df[required_cols]

    conn = duckdb.connect(db_path, read_only=False)
    try:
        # 1. Staging
        conn.register("df_stg", df)
        conn.execute("INSERT INTO staging.macro_policy SELECT * FROM df_stg")
        conn.unregister("df_stg")
        staging_count = len(df)

        # 2. Core
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
        core_new = after_count - before_count

        logger.info(f"Nạp {staging_count} bản ghi vào staging.macro_policy.")
        logger.info(f"Thêm {core_new} bản ghi mới vào core.macro_policy (Tổng hiện tại: {after_count}).")
        return staging_count, core_new
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("=== BẮT ĐẦU CÀO SÂU YAHOO FINANCE TOÀN BỘ CÁC NGÀY (ALL DATES) ===")
    recs = crawl_all_dates_yahoo(max_pages_per_topic=5)
    stg_cnt, core_new = ingest_to_duckdb(recs)
    logger.info(f"Hoàn thành! Staging: {stg_cnt}, CoreNew: {core_new}")
