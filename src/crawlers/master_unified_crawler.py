"""src/crawlers/master_unified_crawler.py

VESTA MASTER UNIFIED CRAWLER & PIPELINE ORCHESTRATOR
Generalizes and coordinates all data collection workflows into a single production pipeline:
1. HAR Offline Ingestion: Parses all captured HAR files in scratch/har/cafef/ (BCTC, disclosures, news).
2. Live BCTC Disclosures Crawler: Fetches real-time company filings & BCTC PDF links from CafeF.
3. Live Financial Category News Crawler: Scrapes 8 financial/macro zones from CafeF (TTCK, BĐS, NH, KTVM...).
4. Vnstock Market Data: Fetches 1-minute OHLCV & tick data (Silver Tier) for watchlist symbols.
5. All ingested records are stored idempotently in db/vesta.duckdb.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_DB_PATH = "db/vesta.duckdb"
HAR_DIR = "scratch/har/cafef"
CAFEF_DISCLOSURE_API = "https://cafef.vn/du-lieu/ajax/ajaxcongbothongtin.ashx"
CAFEF_TIMELINE_URL = "https://cafef.vn/timelinelist/{zone_id}/{page}.chn"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (VESTA-Quant/3.0)",
    "Referer": "https://cafef.vn/",
    "Accept": "*/*"
}

# 8 Core CafeF Category Zones
CAFEF_ZONES = {
    "18831": "Thị trường chứng khoán (TTCK)",
    "18832": "Bất động sản (BĐS)",
    "18833": "Doanh nghiệp (DN)",
    "18834": "Ngân hàng (NH)",
    "18835": "Tài chính quốc tế (TCQT)",
    "18836": "Kinh tế vĩ mô (KTVM)",
    "18839": "Kinh tế số & Công nghệ (KTSO)",
    "188127": "Thị trường hàng hóa & Tiêu dùng"
}


# =============================================================================
# 1. DATABASE SCHEMA INITIALIZATION (IDEMPOTENT)
# =============================================================================
def init_all_database_tables(con: duckdb.DuckDBPyConnection):
    """Initializes schemas and all necessary storage tables."""
    con.execute("""
    CREATE SCHEMA IF NOT EXISTS staging;
    CREATE SCHEMA IF NOT EXISTS core;
    CREATE SCHEMA IF NOT EXISTS meta;

    -- Meta progress table for pipeline orchestration
    CREATE TABLE IF NOT EXISTS meta.crawl_progress (
        dataset_name  VARCHAR NOT NULL,
        symbol        VARCHAR NOT NULL,
        status        VARCHAR NOT NULL,
        retry_count   INTEGER NOT NULL DEFAULT 0,
        last_attempt  TIMESTAMP,
        PRIMARY KEY (dataset_name, symbol)
    );

    -- Corporate disclosures & BCTC PDF reports
    CREATE TABLE IF NOT EXISTS core.cafef_disclosures (
        doc_id          VARCHAR NOT NULL PRIMARY KEY,
        symbol          VARCHAR NOT NULL,
        company_name    VARCHAR,
        trade_center_id INTEGER,
        exchange        VARCHAR,
        year            INTEGER,
        quarter         INTEGER,
        report_type     VARCHAR,
        content         VARCHAR,
        file_name       VARCHAR,
        file_url        VARCHAR,
        lnstctm         DOUBLE,
        published_at    TIMESTAMP,
        raw_json        VARCHAR,
        fetched_at      TIMESTAMP NOT NULL
    );

    -- Corporate events calendar
    CREATE TABLE IF NOT EXISTS core.corporate_events (
        symbol       VARCHAR NOT NULL,
        event_id     VARCHAR NOT NULL,
        event_type   VARCHAR NOT NULL,
        event_date   DATE,
        detail_json  VARCHAR NOT NULL,
        fetched_at   TIMESTAMP NOT NULL,
        PRIMARY KEY (symbol, event_id)
    );

    -- News table
    CREATE TABLE IF NOT EXISTS core.news (
        symbol       VARCHAR NOT NULL,
        source       VARCHAR NOT NULL,
        published_at TIMESTAMP NOT NULL,
        available_at TIMESTAMP NOT NULL,
        headline     VARCHAR NOT NULL,
        url          VARCHAR NOT NULL,
        summary      VARCHAR,
        raw_html     VARCHAR,
        fetched_at   TIMESTAMP NOT NULL,
        PRIMARY KEY (source, url)
    );

    -- 1-Minute OHLCV intraday storage
    CREATE TABLE IF NOT EXISTS core.market_ohlcv_1m (
        symbol     VARCHAR NOT NULL,
        time       TIMESTAMP NOT NULL,
        open       DOUBLE,
        high       DOUBLE,
        low        DOUBLE,
        close      DOUBLE,
        volume     BIGINT,
        fetched_at TIMESTAMP NOT NULL,
        PRIMARY KEY (symbol, time)
    );
    """)


# =============================================================================
# 2. MODULE 1: HAR BATCH OFFLINE INGESTER
# =============================================================================
def parse_create_date(date_str: Optional[str]) -> Optional[datetime.datetime]:
    if not date_str:
        return None
    match = re.search(r"/Date\((\d+)\)/", str(date_str))
    if match:
        ts_ms = int(match.group(1))
        return datetime.datetime.fromtimestamp(ts_ms / 1000.0) if ts_ms > 1e11 else datetime.datetime.fromtimestamp(ts_ms)
    return None


def map_exchange(center_id: Optional[int]) -> str:
    if center_id == 1:
        return "HOSE"
    elif center_id == 2:
        return "HNX"
    elif center_id == 9:
        return "UPCOM"
    return "OTHER"


def run_har_offline_ingestion(con: duckdb.DuckDBPyConnection) -> int:
    """Scans and ingests all CafeF HAR files into core tables."""
    print("\n" + "=" * 80)
    print(">>> [MODULE 1] BẮT ĐẦU NẠP DỮ LIỆU OFFLINE TỪ CÁC FILE .HAR...")
    print("=" * 80)
    
    har_files = glob.glob(os.path.join(HAR_DIR, "*.har"))
    print(f" -> Tìm thấy {len(har_files)} file .har trong thư mục {HAR_DIR}")
    
    total_disclosures = 0
    now = datetime.datetime.now()

    for hf in sorted(har_files):
        fname = os.path.basename(hf)
        try:
            with open(hf, "r", encoding="utf-8", errors="ignore") as f:
                har_data = json.load(f)
            
            entries = har_data.get("log", {}).get("entries", [])
            extracted = []
            
            for e in entries:
                url = e.get("request", {}).get("url", "")
                if "ajaxcongbothongtin.ashx" in url:
                    text = e.get("response", {}).get("content", {}).get("text", "")
                    if text:
                        try:
                            payload = json.loads(text)
                            bctc_list = payload.get("Data", {}).get("BctcList", [])
                            for item in bctc_list:
                                doc_id = str(item.get("Id", "")).strip()
                                if not doc_id:
                                    continue
                                center_id = item.get("TradeCenterId")
                                link = item.get("LinkFile", "")
                                full_url = f"https://cafef.vn{link}" if link and link.startswith("/") else link
                                
                                extracted.append({
                                    "doc_id": doc_id,
                                    "symbol": str(item.get("Symbol", "")).strip().upper(),
                                    "company_name": item.get("CompanyName"),
                                    "trade_center_id": center_id,
                                    "exchange": map_exchange(center_id),
                                    "year": item.get("Year"),
                                    "quarter": item.get("Quarter"),
                                    "report_type": item.get("ReportType"),
                                    "content": item.get("Content"),
                                    "file_name": item.get("FileName"),
                                    "file_url": full_url,
                                    "lnstctm": float(item.get("Lnstctm", 0)) if item.get("Lnstctm") is not None else None,
                                    "published_at": parse_create_date(item.get("CreateDate")),
                                    "raw_json": json.dumps(item, ensure_ascii=False),
                                    "fetched_at": now
                                })
                        except Exception:
                            pass
            
            if extracted:
                df = pd.DataFrame(extracted).drop_duplicates(subset=["doc_id"])
                con.register("df_har", df)
                con.execute("INSERT INTO core.cafef_disclosures SELECT * FROM df_har ON CONFLICT (doc_id) DO NOTHING;")
                con.execute("""
                INSERT INTO core.corporate_events (symbol, event_id, event_type, event_date, detail_json, fetched_at)
                SELECT symbol, doc_id as event_id, 'BCTC_DISCLOSURE' as event_type, CAST(published_at AS DATE) as event_date, raw_json as detail_json, fetched_at
                FROM df_har WHERE symbol IS NOT NULL AND doc_id IS NOT NULL
                ON CONFLICT (symbol, event_id) DO NOTHING;
                """)
                total_disclosures += len(df)
                print(f"    + [{fname:<35}] Nạp thành công {len(df):>3} bản ghi công bố.")
        except Exception as e:
            print(f"    x [{fname:<35}] Lỗi: {e}")

    print(f" -> [MODULE 1 XONG] Tổng số bản ghi công bố BCTC đã nạp: {total_disclosures:,}")
    return total_disclosures


# =============================================================================
# 3. MODULE 2: LIVE BCTC & DISCLOSURES CRAWLER
# =============================================================================
def run_live_disclosures_crawler(con: duckdb.DuckDBPyConnection, max_pages: int = 5, symbol: str = "", delay: float = 0.8) -> int:
    """Crawls live corporate disclosures from CafeF API."""
    print("\n" + "=" * 80)
    print(f">>> [MODULE 2] CÀO TRỰC TIẾP CÔNG BỐ THÔNG TIN & BCTC MỚI NHẤT (Tối đa {max_pages} trang)...")
    print("=" * 80)
    
    total_new = 0
    now = datetime.datetime.now()

    for page in range(1, max_pages + 1):
        url = f"{CAFEF_DISCLOSURE_API}?symbol={symbol}&pageindex={page}&pagesize=20&reporttype=&startdate=&enddate=&center=0"
        try:
            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=12) as res:
                payload = json.loads(res.read().decode("utf-8", errors="ignore"))
                bctc_list = payload.get("Data", {}).get("BctcList", [])
                if not bctc_list:
                    print(f" -> Trang {page}: Hết dữ liệu mới.")
                    break
                
                rows = []
                for item in bctc_list:
                    doc_id = str(item.get("Id", "")).strip()
                    if not doc_id:
                        continue
                    center_id = item.get("TradeCenterId")
                    link = item.get("LinkFile", "")
                    full_url = f"https://cafef.vn{link}" if link and link.startswith("/") else link
                    rows.append({
                        "doc_id": doc_id,
                        "symbol": str(item.get("Symbol", "")).strip().upper(),
                        "company_name": item.get("CompanyName"),
                        "trade_center_id": center_id,
                        "exchange": map_exchange(center_id),
                        "year": item.get("Year"),
                        "quarter": item.get("Quarter"),
                        "report_type": item.get("ReportType"),
                        "content": item.get("Content"),
                        "file_name": item.get("FileName"),
                        "file_url": full_url,
                        "lnstctm": float(item.get("Lnstctm", 0)) if item.get("Lnstctm") is not None else None,
                        "published_at": parse_create_date(item.get("CreateDate")),
                        "raw_json": json.dumps(item, ensure_ascii=False),
                        "fetched_at": now
                    })
                
                df_page = pd.DataFrame(rows)
                con.register("df_live", df_page)
                con.execute("INSERT INTO core.cafef_disclosures SELECT * FROM df_live ON CONFLICT (doc_id) DO NOTHING;")
                con.execute("""
                INSERT INTO core.corporate_events (symbol, event_id, event_type, event_date, detail_json, fetched_at)
                SELECT symbol, doc_id as event_id, 'BCTC_DISCLOSURE' as event_type, CAST(published_at AS DATE) as event_date, raw_json as detail_json, fetched_at
                FROM df_live WHERE symbol IS NOT NULL AND doc_id IS NOT NULL
                ON CONFLICT (symbol, event_id) DO NOTHING;
                """)
                total_new += len(df_page)
                sample_item = df_page.iloc[0]
                print(f" -> Trang {page}: Cào {len(df_page):>2} bản ghi | Mới nhất: [{sample_item['symbol']}] {sample_item['content'][:40]}...")
            
            time.sleep(delay)
        except Exception as e:
            print(f" -> Lỗi cào trang {page}: {e}")
            break

    print(f" -> [MODULE 2 XONG] Đã cào và lưu thành công {total_new:,} bản ghi BCTC.")
    return total_new


# =============================================================================
# 4. MODULE 3: LIVE CATEGORY NEWS CRAWLER (8 ZONES)
# =============================================================================
def run_live_category_news_crawler(con: duckdb.DuckDBPyConnection, zones: List[str], pages_per_zone: int = 2, delay: float = 0.8) -> int:
    """Scrapes financial news across CafeF category zones."""
    print("\n" + "=" * 80)
    print(f">>> [MODULE 3] CÀO TIN TỨC CHUYÊN MỤC TÀI CHÍNH ({len(zones)} Chuyên mục, {pages_per_zone} trang/mục)...")
    print("=" * 80)

    total_articles = 0
    now = datetime.datetime.now()

    for zone_id in zones:
        zone_name = CAFEF_ZONES.get(zone_id, f"Zone {zone_id}")
        print(f"\n--- Đang cào chuyên mục: {zone_name} (ID: {zone_id}) ---")
        
        for page in range(1, pages_per_zone + 1):
            url = CAFEF_TIMELINE_URL.format(zone_id=zone_id, page=page)
            try:
                req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
                with urllib.request.urlopen(req, timeout=12) as res:
                    html = res.read().decode("utf-8", errors="ignore")
                    soup = BeautifulSoup(html, "html.parser")
                    
                    articles = []
                    items = soup.find_all("div", class_=re.compile(r"tlitem|box-category-item"))
                    
                    for it in items:
                        h3 = it.find(["h3", "h2"])
                        if not h3 or not h3.find("a"):
                            continue
                        a_tag = h3.find("a")
                        title = a_tag.get_text(strip=True)
                        rel_link = a_tag.get("href", "")
                        full_link = urllib.parse.urljoin("https://cafef.vn", rel_link)
                        
                        sapo_tag = it.find("p", class_=re.compile(r"sapo|knswli-sapo"))
                        summary = sapo_tag.get_text(strip=True) if sapo_tag else ""
                        
                        time_tag = it.find(class_=re.compile(r"time|knswli-date"))
                        time_str = time_tag.get_text(strip=True) if time_tag else ""
                        
                        # Extract ticker if in title like "HPG: Lợi nhuận..."
                        ticker_match = re.match(r"^([A-Z0-9]{3,4}):", title)
                        symbol = ticker_match.group(1) if ticker_match else "MARKET"

                        if title and full_link:
                            articles.append({
                                "symbol": symbol,
                                "source": "cafef",
                                "published_at": now,
                                "available_at": now,
                                "headline": title,
                                "body": summary,
                                "source_url": full_link,
                                "fetched_at": now,
                                "duplicate_of": None
                            })

                    if articles:
                        df_news = pd.DataFrame(articles).drop_duplicates(subset=["source_url"])
                        con.register("df_news", df_news)
                        con.execute("""
                        INSERT INTO core.news (symbol, source, published_at, available_at, headline, body, source_url, fetched_at, duplicate_of)
                        SELECT symbol, source, published_at, available_at, headline, body, source_url, fetched_at, duplicate_of FROM df_news
                        ON CONFLICT (source_url) DO NOTHING;
                        """)
                        total_articles += len(df_news)
                        print(f" -> Trang {page}: Thu được {len(df_news):>2} bài báo. Mẫu: {articles[0]['headline'][:45]}...")
                
                time.sleep(delay)
            except Exception as e:
                print(f" -> Lỗi cào trang {page} mục {zone_id}: {e}")
                break

    print(f"\n -> [MODULE 3 XONG] Tổng số bài báo chuyên mục đã lưu: {total_articles:,}")
    return total_articles


# =============================================================================
# 5. MODULE 4: VNSTOCK MARKET DATA (1-MINUTE & TICKS)
# =============================================================================
def run_vnstock_market_crawler(con: duckdb.DuckDBPyConnection, symbols: List[str], interval: str = "1m", length: str = "1M") -> int:
    """Fetches high-resolution market data via vnstock_data."""
    print("\n" + "=" * 80)
    print(f">>> [MODULE 4] CÀO DỮ LIỆU THỊ TRƯỜNG VNSTOCK SILVER (Mã={symbols}, Khung={interval})...")
    print("=" * 80)

    try:
        from vnstock_data import Market
        mkt = Market()
    except ImportError:
        print(" -> [BỎ QUA] vnstock_data chưa được cài đặt trong môi trường này.")
        return 0

    total_bars = 0
    now = datetime.datetime.now()

    for sym in symbols:
        sym = sym.strip().upper()
        try:
            print(f" -> Đang cào mã {sym} (interval={interval}, length={length})...")
            df = mkt.equity(sym).ohlcv(length=length, interval=interval)
            
            if df is not None and not df.empty:
                df['symbol'] = sym
                df['time'] = pd.to_datetime(df['time'])
                df['fetched_at'] = now
                
                # Standardize columns
                req_cols = ['symbol', 'time', 'open', 'high', 'low', 'close', 'volume', 'fetched_at']
                df_to_save = df[req_cols].dropna(subset=['time'])

                con.register("df_mkt", df_to_save)
                con.execute("""
                INSERT INTO core.market_ohlcv_1m 
                SELECT * FROM df_mkt 
                ON CONFLICT (symbol, time) DO NOTHING;
                """)
                total_bars += len(df_to_save)
                print(f"    + [{sym}] Cào thành công {len(df_to_save):,} nến {interval}!")
            else:
                print(f"    x [{sym}] Không có dữ liệu.")
            time.sleep(0.5)
        except Exception as e:
            print(f"    x [{sym}] Lỗi: {e}")

    print(f" -> [MODULE 4 XONG] Đã lưu {total_bars:,} thanh nến thị trường vào core.market_ohlcv_1m.")
    return total_bars


# =============================================================================
# 6. MASTER ORCHESTRATOR & CLI ENTRYPOINT
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="VESTA Master Unified Crawler & Ingestion Pipeline")
    parser.add_argument("--all", action="store_true", help="Chạy toàn bộ quy trình: HAR + Live Disclosures + Live News")
    parser.add_argument("--har-only", action="store_true", help="Chỉ nạp offline từ các file HAR")
    parser.add_argument("--live-disclosures", action="store_true", help="Cào công bố thông tin & BCTC mới từ CafeF")
    parser.add_argument("--live-news", action="store_true", help="Cào tin tức chuyên mục tài chính từ CafeF")
    parser.add_argument("--vnstock", action="store_true", help="Cào nến 1 phút thị trường từ Vnstock")
    parser.add_argument("--pages", type=int, default=3, help="Số trang cào cho mỗi luồng (mặc định: 3)")
    parser.add_argument("--symbols", type=str, default="FPT,HPG,VCB,MWG,SSI", help="Danh sách mã chứng khoán cào nến (cách nhau dấu phẩy)")
    parser.add_argument("--delay", type=float, default=0.8, help="Thời gian nghỉ giữa các request (giây, mặc định: 0.8)")
    args = parser.parse_args()

    # If no flags passed, run default demo (all modules with small pages for safety)
    if not any([args.all, args.har_only, args.live_disclosures, args.live_news, args.vnstock]):
        args.all = True

    start_time = time.time()
    print("\n" + "#" * 85)
    print(" VESTA QUANTITATIVE TRADING — MASTER UNIFIED CRAWLER")
    print(f" Cơ sở dữ liệu đích: {CANONICAL_DB_PATH}")
    print(f" Thời điểm kích hoạt : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#" * 85)

    con = duckdb.connect(CANONICAL_DB_PATH)
    init_all_database_tables(con)

    har_cnt = 0
    disc_cnt = 0
    news_cnt = 0
    mkt_cnt = 0

    # 1. HAR Offline Ingestion
    if args.all or args.har_only:
        har_cnt = run_har_offline_ingestion(con)

    # 2. Live Disclosures
    if args.all or args.live_disclosures:
        disc_cnt = run_live_disclosures_crawler(con, max_pages=args.pages, delay=args.delay)

    # 3. Live News
    if args.all or args.live_news:
        target_zones = list(CAFEF_ZONES.keys())[:4] if args.all else list(CAFEF_ZONES.keys())
        news_cnt = run_live_category_news_crawler(con, zones=target_zones, pages_per_zone=max(1, args.pages // 2), delay=args.delay)

    # 4. Vnstock Market Data
    if args.all or args.vnstock:
        sym_list = [s.strip() for s in args.symbols.split(",") if s.strip()]
        mkt_cnt = run_vnstock_market_crawler(con, symbols=sym_list, interval="1m", length="1M")

    # Print summary of database status
    total_disc_db = con.execute("SELECT count(*) FROM core.cafef_disclosures").fetchone()[0]
    total_events_db = con.execute("SELECT count(*) FROM core.corporate_events").fetchone()[0]
    total_news_db = con.execute("SELECT count(*) FROM core.news").fetchone()[0]
    con.close()

    elapsed = time.time() - start_time
    print("\n" + "=" * 85)
    print(" TỔNG KẾT PHIÊN CÀO DỮ LIỆU TỔNG HỢP VESTA:")
    print("=" * 85)
    print(f" - Tổng thời gian chạy           : {elapsed:.2f} giây")
    print(f" - Dữ liệu nạp từ HAR offline     : {har_cnt:,} bản ghi")
    print(f" - BCTC & Công bố cào trực tiếp  : {disc_cnt:,} bản ghi")
    print(f" - Tin tức chuyên mục cào mới    : {news_cnt:,} bài báo")
    print(f" - Nến thị trường 1m cào mới     : {mkt_cnt:,} thanh nến")
    print("-" * 85)
    print(f" HIỆN TRẠNG DATABASE CHÍNH (db/vesta.duckdb):")
    print(f"  * Bảng core.cafef_disclosures  : {total_disc_db:,} bản ghi BCTC & Công bố")
    print(f"  * Bảng core.corporate_events   : {total_events_db:,} sự kiện doanh nghiệp")
    print(f"  * Bảng core.news               : {total_news_db:,} bài tin tức tài chính")
    print("=" * 85)


if __name__ == "__main__":
    main()
