"""
Yahoo Finance Master Crawler
Crawls:
1. All 107 Editorial Topics (GraphQL GetFinanceTopicStream)
2. Global Company Symbols & Macro Asset News (GraphQL GetQSPLeafNewsStream)
3. Global Breaking Market Notifications & Search News
4. Historical Market Indices & Macro Commodities OHLCV from year 2000 (Chart API)

Target Tables in vesta_latest_backup.duckdb:
- core.macro_policy (News, policy, topic articles)
- core.market_index_daily (Daily OHLCV from year 2000 to present)
"""

import datetime as dt
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any
import duckdb
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yahoo_master_crawler")

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

# 1. Global Macro Assets & Company Symbols
KEY_COMPANIES = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",
    "BRK-B", "JNJ", "V", "WMT", "JPM", "PG", "UNH", "XOM",
    "TSM", "BABA", "ASML", "AMD", "INTC", "QCOM", "VNM"
]

MACRO_INDICES = [
    ("^GSPC", "S&P 500"),
    ("^DJI", "Dow Jones Industrial Average"),
    ("^IXIC", "NASDAQ Composite"),
    ("^RUT", "Russell 2000"),
    ("^VIX", "CBOE Volatility Index"),
    ("CL=F", "Crude Oil WTI"),
    ("BZ=F", "Brent Crude Oil"),
    ("GC=F", "Gold Futures"),
    ("SI=F", "Silver Futures"),
    ("HG=F", "Copper Futures"),
    ("DX-Y.NYB", "US Dollar Index"),
    ("USDVND=X", "USD / VND Exchange Rate"),
    ("EURUSD=X", "EUR / USD Exchange Rate"),
    ("^TNX", "10-Year US Treasury Yield"),
    ("^TYX", "30-Year US Treasury Yield"),
    ("VNM", "VanEck Vietnam ETF")
]


def load_all_editorial_topics() -> list[tuple[str, str, str]]:
    """Loads all 107 editorial topics from HAR metadata."""
    har_path = Path("d:/VESTA/scratch/har/yahoo_finance/finance.yahoo.com-News.har")
    if not har_path.exists():
        return []
    try:
        with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        for e in data["log"]["entries"]:
            txt = e["response"].get("content", {}).get("text", "")
            if "editorialTopics" in e["request"]["url"] and "cdsData" in txt:
                js = json.loads(txt)
                topics = js.get("data", {}).get("cdsData", {}).get("topics", [])
                results = []
                for t in topics:
                    if t.get("listId"):
                        results.append((t.get("topicName"), t.get("title"), t.get("listId")))
                return results
    except Exception as e:
        logger.warning(f"Không thể đọc topic list từ HAR: {e}")
    return []


def crawl_news_from_all_sources(max_pages_per_topic: int = 4) -> list[dict[str, Any]]:
    """Crawls all news from editorial topics, company symbols, and macro indices."""
    now = dt.datetime.now(dt.timezone.utc)
    articles_map = {}

    # A. Crawl all editorial topics (107 topics)
    all_topics = load_all_editorial_topics()
    logger.info(f"=== [LUỒNG 1] Cào {len(all_topics)} Chuyên mục Biên tập (Editorial Topics) ===")
    for idx, (tname, title, tuuid) in enumerate(all_topics):
        logger.info(f"[{idx+1}/{len(all_topics)}] Quét topic: {tname} ({title})...")
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
                    atitle = asset.get("title")
                    attrs = asset.get("contentAttributes", {})
                    url = attrs.get("canonicalUrl") or attrs.get("clickthroughUrl")
                    pub_str = attrs.get("pubDate")
                    provider = (attrs.get("provider") or {}).get("displayName") or "Yahoo Finance"
                    summary = attrs.get("summary") or atitle

                    if not url or not atitle or url in articles_map:
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
                        "headline": atitle.strip(),
                        "summary": summary.strip()[:1000] if summary else atitle.strip(),
                        "body": summary.strip() if summary else atitle.strip(),
                        "source_url": url.strip(),
                        "fetched_at": now,
                    }
                time.sleep(0.1)
            except Exception:
                break

    logger.info(f"Tổng bài viết sau khi quét chuyên mục: {len(articles_map)}")

    # B. Crawl Company Symbols & Global Asset News
    logger.info("=== [LUỒNG 2] Cào Tin tức theo Mã Cổ phiếu & Tài sản Toàn cầu ===")
    all_syms = KEY_COMPANIES + [code for code, _ in MACRO_INDICES]
    # Chunk symbols into groups of 5
    chunk_size = 5
    for i in range(0, len(all_syms), chunk_size):
        chunk = all_syms[i:i + chunk_size]
        logger.info(f"-> Quét tin tức rổ mã: {chunk}...")
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
                        "queryVariables": {"tickerSymbol": chunk},
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
                    atitle = asset.get("title")
                    attrs = asset.get("contentAttributes", {})
                    url = attrs.get("canonicalUrl") or attrs.get("clickthroughUrl")
                    pub_str = attrs.get("pubDate")
                    provider = (attrs.get("provider") or {}).get("displayName") or "Yahoo Finance"
                    summary = attrs.get("summary") or atitle

                    if not url or not atitle or url in articles_map:
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
                        "headline": atitle.strip(),
                        "summary": summary.strip()[:1000] if summary else atitle.strip(),
                        "body": summary.strip() if summary else atitle.strip(),
                        "source_url": url.strip(),
                        "fetched_at": now,
                    }
                time.sleep(0.1)
            except Exception:
                break

    # C. Activity Feed (200 items)
    logger.info("=== [LUỒNG 3] Cào Breaking Activity Feed ===")
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

    # D. Topic Search News
    logger.info("=== [LUỒNG 4] Cào Topic Search News ===")
    queries = ["Fed", "interest rates", "Vietnam", "tariffs", "oil", "inflation", "semiconductor", "dollar index"]
    for q in queries:
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
            time.sleep(0.1)
        except Exception:
            pass

    records = list(articles_map.values())
    logger.info(f"TỔNG KẾT BÀI VIẾT: {len(records)} bài viết Yahoo Finance không trùng lặp.")
    return records


def crawl_historical_indices_ohlcv(start_year: int = 2000) -> list[dict[str, Any]]:
    """Crawls daily historical OHLCV from start_year (e.g. 2000) for global market indices & assets."""
    p1 = int(dt.datetime(start_year, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.now(dt.timezone.utc).timestamp())
    now = dt.datetime.now(dt.timezone.utc)

    all_bars = []
    logger.info(f"=== [LUỒNG 5] Cào Dữ liệu Giá & Chỉ số Toàn cầu từ năm {start_year} đến nay ===")
    
    for symbol, name in MACRO_INDICES:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d"
        try:
            resp = requests.get(url, headers=API_HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Lỗi tải OHLCV {symbol} ({resp.status_code})")
                continue
            data = resp.json()
            res = data.get("chart", {}).get("result", [])
            if not res:
                continue
            chart_res = res[0]
            timestamps = chart_res.get("timestamp", [])
            indicators = chart_res.get("indicators", {}).get("quote", [{}])[0]
            opens = indicators.get("open", [])
            highs = indicators.get("high", [])
            lows = indicators.get("low", [])
            closes = indicators.get("close", [])
            volumes = indicators.get("volume", [])

            valid_count = 0
            for i, ts in enumerate(timestamps):
                c = closes[i] if i < len(closes) else None
                if c is None:
                    continue
                o = opens[i] if i < len(opens) and opens[i] is not None else c
                h = highs[i] if i < len(highs) and highs[i] is not None else c
                l = lows[i] if i < len(lows) and lows[i] is not None else c
                v = int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0

                bar_date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
                all_bars.append({
                    "index_code": symbol,
                    "date": bar_date,
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": v,
                    "fetched_at": now
                })
                valid_count += 1

            logger.info(f"-> {symbol} ({name}): Lấy thành công {valid_count:,} phiên giao dịch từ {start_year}.")
            time.sleep(0.2)
        except Exception as e:
            logger.warning(f"Lỗi khi cào {symbol}: {e}")

    logger.info(f"TỔNG KẾT OHLCV: Lấy được tổng cộng {len(all_bars):,} phiên giao dịch lịch sử.")
    return all_bars


def save_all_to_duckdb(news_records: list[dict[str, Any]], ohlcv_records: list[dict[str, Any]], db_path: str = DB_PATH):
    """Saves both news articles and historical index bars to DuckDB."""
    conn = duckdb.connect(db_path, read_only=False)
    try:
        # 1. Save News into staging & core.macro_policy
        if news_records:
            df_news = pd.DataFrame(news_records)
            required_cols = [
                "source", "issuing_body", "doc_type", "doc_number",
                "published_at", "available_at", "headline", "summary",
                "body", "source_url", "fetched_at"
            ]
            df_news = df_news[required_cols]
            
            conn.register("df_news_stg", df_news)
            conn.execute("INSERT INTO staging.macro_policy SELECT * FROM df_news_stg")
            conn.unregister("df_news_stg")

            before_news = conn.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()[0]
            conn.register("df_news_core", df_news)
            conn.execute("""
                INSERT INTO core.macro_policy
                SELECT * FROM df_news_core
                ON CONFLICT (source_url) DO UPDATE SET
                    headline = EXCLUDED.headline,
                    summary = EXCLUDED.summary,
                    body = EXCLUDED.body,
                    fetched_at = EXCLUDED.fetched_at
            """)
            conn.unregister("df_news_core")
            after_news = conn.execute("SELECT count(*) FROM core.macro_policy WHERE source = 'yahoo_finance'").fetchone()[0]
            logger.info(f"[NEWS] Nạp {len(df_news):,} bài vào staging. Thêm {after_news - before_news:,} bài mới vào core.macro_policy (Tổng hiện tại: {after_news:,}).")

        # 2. Save Historical Market Index Bars into core.market_index_daily
        if ohlcv_records:
            df_bars = pd.DataFrame(ohlcv_records)
            before_bars = conn.execute("SELECT count(*) FROM core.market_index_daily").fetchone()[0]
            conn.register("df_bars_core", df_bars)
            conn.execute("""
                INSERT INTO core.market_index_daily
                SELECT * FROM df_bars_core
                ON CONFLICT (index_code, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    fetched_at = EXCLUDED.fetched_at
            """)
            conn.unregister("df_bars_core")
            after_bars = conn.execute("SELECT count(*) FROM core.market_index_daily").fetchone()[0]
            logger.info(f"[OHLCV] Thêm {after_bars - before_bars:,} phiên mới vào core.market_index_daily (Tổng hiện tại: {after_bars:,}).")

    finally:
        conn.close()


def run_master_crawl(max_pages_per_topic: int = 3, start_year: int = 2000):
    """Executes full master crawl."""
    logger.info("=========================================================================")
    logger.info(f">>> BẮT ĐẦU CÀO TOÀN DIỆN YAHOO FINANCE (TOPICS, SYMBOLS, GLOBAL NEWS, TỪ NĂM {start_year}) <<<")
    logger.info("=========================================================================")
    
    # 1. Crawl all news
    news = crawl_news_from_all_sources(max_pages_per_topic=max_pages_per_topic)
    
    # 2. Crawl historical OHLCV from 2000
    bars = crawl_historical_indices_ohlcv(start_year=start_year)
    
    # 3. Save to DuckDB
    save_all_to_duckdb(news, bars)
    logger.info(">>> TOÀN BỘ DỮ LIỆU ĐÃ ĐƯỢC LƯU AN TOÀN VÀO DUCKDB <<<")


if __name__ == "__main__":
    run_master_crawl(max_pages_per_topic=3, start_year=2000)
