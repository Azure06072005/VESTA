"""src/crawlers/crawl_cafef_disclosures_max.py

Crawls ALL pages (up to 7,583 pages, 151,648 records) of CafeF BCTC Disclosures.
Uses pagesize=100 for 5x acceleration.
Saves into a DEDICATED database (db/vesta_crawled_fresh.duckdb) to prevent file locks.
"""
from __future__ import annotations

import argparse
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

FRESH_DB_PATH = "db/vesta_crawled_fresh.duckdb"
API_BASE_URL = "https://cafef.vn/du-lieu/ajax/ajaxcongbothongtin.ashx"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://cafef.vn/du-lieu/cong-bo-thong-tin.chn",
    "Accept": "*/*"
}


def init_tables(con: duckdb.DuckDBPyConnection):
    con.execute("""
    CREATE TABLE IF NOT EXISTS cafef_disclosures (
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

    CREATE TABLE IF NOT EXISTS crawl_progress (
        dataset_name  VARCHAR NOT NULL,
        last_page     INTEGER NOT NULL,
        total_records INTEGER NOT NULL,
        updated_at    TIMESTAMP NOT NULL,
        PRIMARY KEY (dataset_name)
    );
    """)


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


def transform_bctc_item(item: Dict[str, Any], fetched_at: datetime.datetime) -> Dict[str, Any]:
    doc_id = str(item.get("Id", "")).strip()
    symbol = str(item.get("Symbol", "")).strip().upper()
    center_id = item.get("TradeCenterId")
    link = item.get("LinkFile", "")
    full_url = f"https://cafef.vn{link}" if link and link.startswith("/") else link

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
        "published_at": parse_create_date(item.get("CreateDate")),
        "raw_json": json.dumps(item, ensure_ascii=False),
        "fetched_at": fetched_at
    }


def crawl_all_disclosures(start_page: int = 1, max_pages: Optional[int] = None, page_size: int = 100, delay: float = 0.6):
    """
    Crawls CafeF disclosures exhaustively.
    - page_size=100 accelerates crawling by 5x (only ~1,517 requests for all 151,648 filings).
    """
    print("=" * 85)
    print("CÀO TOÀN BỘ CÔNG BỐ THÔNG TIN & BCTC CAFEF (VÉT CẠN MAX PAGES)")
    print(f"Cơ sở dữ liệu độc lập: {FRESH_DB_PATH} (Tránh xung đột tiến trình)")
    print(f"Bắt đầu từ trang: {start_page} | Kích thước mỗi trang: {page_size} bản ghi")
    print("=" * 85)

    con = duckdb.connect(FRESH_DB_PATH)
    init_tables(con)

    # Resume from last page if recorded
    if start_page == 1:
        prog = con.execute("SELECT last_page FROM crawl_progress WHERE dataset_name = 'cafef_disclosures'").fetchone()
        if prog:
            start_page = prog[0] + 1
            print(f" -> Tìm thấy tiến độ trước đó! Tiếp tục cào từ trang {start_page}...")

    page = start_page
    total_new = 0
    now = datetime.datetime.now()

    while True:
        if max_pages and page > (start_page + max_pages - 1):
            print(f"\n -> Đạt giới hạn {max_pages} trang theo yêu cầu.")
            break

        url = f"{API_BASE_URL}?symbol=&pageindex={page}&pagesize={page_size}&reporttype=&startdate=&enddate=&center=0"
        try:
            req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as res:
                payload = json.loads(res.read().decode("utf-8", errors="ignore"))
                data = payload.get("Data", {})
                bctc_list = data.get("BctcList", [])
                total_server_count = data.get("Count", 0)

                if not bctc_list:
                    print(f"\n -> [HẾT DỮ LIỆU] Trang {page} trả về rỗng. Đã cào tới trang cuối cùng của CafeF!")
                    break

                rows = [transform_bctc_item(item, now) for item in bctc_list if item.get("Id")]
                df_page = pd.DataFrame(rows).drop_duplicates(subset=["doc_id"])

                con.register("df_page", df_page)
                con.execute("INSERT INTO cafef_disclosures SELECT * FROM df_page ON CONFLICT (doc_id) DO NOTHING;")

                total_new += len(df_page)
                total_in_db = con.execute("SELECT count(*) FROM cafef_disclosures").fetchone()[0]

                # Update progress
                con.execute(f"""
                INSERT INTO crawl_progress (dataset_name, last_page, total_records, updated_at)
                VALUES ('cafef_disclosures', {page}, {total_in_db}, '{datetime.datetime.now()}')
                ON CONFLICT (dataset_name) DO UPDATE SET
                    last_page = EXCLUDED.last_page,
                    total_records = EXCLUDED.total_records,
                    updated_at = EXCLUDED.updated_at;
                """)

                max_page_est = (total_server_count // page_size) + 1 if total_server_count else "?"
                print(f" -> [Trang {page:>4}/{max_page_est}] Cào +{len(df_page):>3} bản ghi | Tổng DB: {total_in_db:,} / Server: {total_server_count:,} | Mới nhất: [{rows[0]['symbol']}] {rows[0]['content'][:30]}...")

            page += 1
            time.sleep(delay)
        except Exception as e:
            print(f" -> Lỗi tại trang {page}: {e}. Đang tạm nghỉ 3s trước khi thử lại...")
            time.sleep(3)
            # Re-try same page once
            continue

    con.close()
    print("\n" + "=" * 85)
    print(f"HOÀN TẤT PHIÊN CÀO BCTC! Đã lưu {total_new:,} bản ghi mới vào {FRESH_DB_PATH}.")
    print("=" * 85)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cào toàn bộ BCTC CafeF max pages")
    parser.add_argument("--pages", type=int, default=None, help="Giới hạn số trang (để trống để cào vét cạn toàn bộ 7,583 trang)")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu")
    parser.add_argument("--page-size", type=int, default=100, help="Kích thước mỗi trang (mặc định: 100 để tăng tốc gấp 5 lần)")
    parser.add_argument("--delay", type=float, default=0.6, help="Thời gian nghỉ (giây)")
    args = parser.parse_args()

    crawl_all_disclosures(start_page=args.start_page, max_pages=args.pages, page_size=args.page_size, delay=args.delay)
