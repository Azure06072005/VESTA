"""src/crawlers/crawl_cafef_disclosures.py

Crawls and ingests CafeF BCTC and Corporate Disclosures into db/vesta.duckdb.
Supports two modes:
1. Ingest offline from scratch/har/cafef/cafef_du-lieu_thong-tin-bctc.har
2. Live incremental crawler calling https://cafef.vn/du-lieu/ajax/ajaxcongbothongtin.ashx
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

CANONICAL_DB_PATH = "db/vesta.duckdb"
HAR_PATH = "scratch/har/cafef/cafef_du-lieu_thong-tin-bctc.har"
API_BASE_URL = "https://cafef.vn/du-lieu/ajax/ajaxcongbothongtin.ashx"


def init_disclosure_tables(con: duckdb.DuckDBPyConnection):
    """Initializes staging.cafef_disclosures and core.cafef_disclosures tables."""
    con.execute("""
    CREATE SCHEMA IF NOT EXISTS staging;
    CREATE SCHEMA IF NOT EXISTS core;

    CREATE TABLE IF NOT EXISTS staging.cafef_disclosures (
        doc_id          VARCHAR,
        symbol          VARCHAR,
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
    """)


def parse_create_date(date_str: Optional[str]) -> Optional[datetime.datetime]:
    """Parses CafeF /Date(1789371082789)/ format into Python datetime."""
    if not date_str:
        return None
    match = re.search(r"/Date\((\d+)\)/", str(date_str))
    if match:
        ts_ms = int(match.group(1))
        # Handle ms vs s
        if ts_ms > 1e11:
            return datetime.datetime.fromtimestamp(ts_ms / 1000.0)
        return datetime.datetime.fromtimestamp(ts_ms)
    return None


def map_exchange(center_id: Optional[int]) -> str:
    """Maps trade center id to exchange code."""
    if center_id == 1:
        return "HOSE"
    elif center_id == 2:
        return "HNX"
    elif center_id == 9:
        return "UPCOM"
    return "OTHER"


def transform_bctc_item(item: Dict[str, Any], fetched_at: datetime.datetime) -> Dict[str, Any]:
    """Transforms raw CafeF BCTC item into database row."""
    doc_id = str(item.get("Id", "")).strip()
    symbol = str(item.get("Symbol", "")).strip().upper()
    center_id = item.get("TradeCenterId")
    link = item.get("LinkFile", "")
    full_url = f"https://cafef.vn{link}" if link and link.startswith("/") else link

    pub_at = parse_create_date(item.get("CreateDate"))

    return {
        "doc_id": doc_id,
        "symbol": symbol,
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
        "published_at": pub_at,
        "raw_json": json.dumps(item, ensure_ascii=False),
        "fetched_at": fetched_at
    }


def ingest_from_har(har_path: str = HAR_PATH) -> int:
    """Ingests disclosures captured in HAR file into database."""
    print(f"\n>>> [1/2] Ingesting disclosures from HAR file: {har_path}...")
    if not os.path.exists(har_path):
        print(f"File not found: {har_path}")
        return 0

    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        har_data = json.load(f)

    entries = har_data.get("log", {}).get("entries", [])
    extracted_rows = []
    now = datetime.datetime.now()

    for e in entries:
        url = e.get("request", {}).get("url", "")
        if "ajaxcongbothongtin.ashx" in url:
            text = e.get("response", {}).get("content", {}).get("text", "")
            if text:
                try:
                    payload = json.loads(text)
                    bctc_list = payload.get("Data", {}).get("BctcList", [])
                    for item in bctc_list:
                        row = transform_bctc_item(item, now)
                        if row["doc_id"]:
                            extracted_rows.append(row)
                except Exception as ex:
                    pass

    print(f" -> Found {len(extracted_rows)} disclosure records in HAR file.")
    if not extracted_rows:
        return 0

    df = pd.DataFrame(extracted_rows).drop_duplicates(subset=["doc_id"])
    print(f" -> Deduplicated down to {len(df)} distinct disclosure records.")

    con = duckdb.connect(CANONICAL_DB_PATH)
    init_disclosure_tables(con)

    # Insert into staging
    con.register("df_staging", df)
    con.execute("INSERT INTO staging.cafef_disclosures SELECT * FROM df_staging")

    # Upsert into core (ON CONFLICT DO NOTHING)
    con.execute("""
    INSERT INTO core.cafef_disclosures 
    SELECT * FROM df_staging
    ON CONFLICT (doc_id) DO NOTHING;
    """)

    # Also upsert into core.corporate_events as BCTC_DISCLOSURE events
    con.execute("""
    INSERT INTO core.corporate_events (symbol, event_id, event_type, event_date, detail_json, fetched_at)
    SELECT 
        symbol,
        doc_id as event_id,
        'BCTC_DISCLOSURE' as event_type,
        CAST(published_at AS DATE) as event_date,
        raw_json as detail_json,
        fetched_at
    FROM df_staging
    WHERE symbol IS NOT NULL AND doc_id IS NOT NULL
    ON CONFLICT (symbol, event_id) DO NOTHING;
    """)

    core_cnt = con.execute("SELECT count(*) FROM core.cafef_disclosures").fetchone()[0]
    con.close()

    print(f" -> [OK] Ingested into core.cafef_disclosures! Total rows in DB: {core_cnt:,}")
    return len(df)


def crawl_live_disclosures(max_pages: int = 5, symbol: str = "", delay: float = 0.8) -> int:
    """
    Crawls live disclosures from CafeF API and saves to main database.
    param max_pages: Number of pages to crawl
    param symbol: Specific symbol or empty string for all market
    param delay: Delay in seconds between requests to avoid rate limits
    """
    print(f"\n>>> [2/2] Crawling live disclosures from CafeF API (Pages: 1 to {max_pages}, Symbol='{symbol}')...")
    con = duckdb.connect(CANONICAL_DB_PATH)
    init_disclosure_tables(con)

    total_inserted = 0
    now = datetime.datetime.now()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": "https://cafef.vn/du-lieu/cong-bo-thong-tin.chn",
        "Accept": "*/*"
    }

    for page in range(1, max_pages + 1):
        url = f"{API_BASE_URL}?symbol={symbol}&pageindex={page}&pagesize=20&reporttype=&startdate=&enddate=&center=0"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                content = response.read().decode("utf-8", errors="ignore")
                payload = json.loads(content)
                bctc_list = payload.get("Data", {}).get("BctcList", [])
                
                if not bctc_list:
                    print(f" -> Trang {page}: Không còn dữ liệu mới.")
                    break

                rows = [transform_bctc_item(item, now) for item in bctc_list if item.get("Id")]
                df_page = pd.DataFrame(rows)

                con.register("df_page", df_page)
                con.execute("""
                INSERT INTO core.cafef_disclosures 
                SELECT * FROM df_page
                ON CONFLICT (doc_id) DO NOTHING;
                """)
                
                con.execute("""
                INSERT INTO core.corporate_events (symbol, event_id, event_type, event_date, detail_json, fetched_at)
                SELECT 
                    symbol,
                    doc_id as event_id,
                    'BCTC_DISCLOSURE' as event_type,
                    CAST(published_at AS DATE) as event_date,
                    raw_json as detail_json,
                    fetched_at
                FROM df_page
                WHERE symbol IS NOT NULL AND doc_id IS NOT NULL
                ON CONFLICT (symbol, event_id) DO NOTHING;
                """)

                total_inserted += len(df_page)
                print(f" -> Trang {page}: Cào thành công {len(df_page)} bản ghi (Mã mới nhất: {df_page.iloc[0]['symbol']} - {df_page.iloc[0]['content'][:35]}...).")

            time.sleep(delay)
        except Exception as e:
            print(f" -> Lỗi trang {page}: {e}")
            break

    total_cnt = con.execute("SELECT count(*) FROM core.cafef_disclosures").fetchone()[0]
    con.close()
    print(f"\n -> [HOÀN TẤT] Tổng số bản ghi trong core.cafef_disclosures: {total_cnt:,}")
    return total_inserted


if __name__ == "__main__":
    print("=" * 85)
    print("CAFEF BCTC & CORPORATE DISCLOSURE CRAWLER")
    print(f"Database: {CANONICAL_DB_PATH}")
    print("=" * 85)

    # 1. Ingest offline captured records from HAR
    har_count = ingest_from_har(HAR_PATH)

    # 2. Crawl 3 pages of live disclosures as verification
    live_count = crawl_live_disclosures(max_pages=3, delay=0.5)

    print("\n" + "=" * 85)
    print("TỔNG KẾT TIẾN TRÌNH:")
    print(f" - Bản ghi nạp từ file HAR : {har_count}")
    print(f" - Bản ghi cào trực tiếp   : {live_count}")
    print("=" * 85)
