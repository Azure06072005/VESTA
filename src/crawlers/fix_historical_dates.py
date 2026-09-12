"""Date Fixer for BaoDauTu and ThoiBaoNganHang.

File: src/crawlers/fix_historical_dates.py
Mục đích:
    Sửa lỗi bắt nhầm selector ngày ở header banner (.date_top và .system-date)
    khiến 31.339 bài viết lịch sử từ 2014-2026 bị gán sai thành ngày chạy crawler (05/09/2026).
    
Cách hoạt động:
    1. Đọc danh sách source_url bị lỗi từ core.macro_policy.
    2. Đa luồng lấy thẻ ngày thật (.post-time cho Báo Đầu tư, .article-date cho Thời báo Ngân hàng).
    3. Cập nhật trực tiếp published_at chuẩn xác vào database.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import logging
from pathlib import Path
import re
import sys
import time
from typing import Any

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger("fix_historical_dates")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Date-Repair)"
HEADERS = {"User-Agent": USER_AGENT}


def extract_true_date(url: str, source: str, session: requests.Session) -> tuple[str, dt.datetime | None]:
    """Tải nhanh HTML và bóc tách ngày công bố bài viết thực tế (loại bỏ header)."""
    try:
        r = session.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return url, None
        soup = BeautifulSoup(r.text, "html.parser")

        # 1. Thử meta chuẩn
        meta = soup.find("meta", property="article:published_time") or soup.find("meta", property="og:updated_time")
        if meta and meta.get("content"):
            try:
                dt_obj = dt.datetime.fromisoformat(meta["content"].replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)
                return url, dt_obj
            except Exception:
                pass

        # 2. Xử lý theo từng nguồn
        if source == "baodautu":
            el = soup.select_one(".post-time, .author-share-top")
            if el:
                m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", el.text)
                if m:
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    hh = int(m.group(4)) if m.group(4) else 8
                    mm = int(m.group(5)) if m.group(5) else 0
                    return url, dt.datetime(y, mo, d, hh, mm) - dt.timedelta(hours=7)

        elif source == "thoibaonganhang":
            el = soup.select_one(".article-date, .format_date")
            if el:
                m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", el.text)
                if m:
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    return url, dt.datetime(y, mo, d, 8, 0) - dt.timedelta(hours=7)

    except Exception as e:
        logger.debug(f"Lỗi tải {url}: {e}")

    return url, None


def fix_dates(
    db_path: str = "d:/VESTA/db/vesta.duckdb",
    source: str = "baodautu",
    limit: int = 100,
    workers: int = 10,
) -> int:
    """Thực hiện vá ngày cho một nguồn chỉ định."""
    con = duckdb.connect(db_path, read_only=False)
    
    # Lấy danh sách URL bị kẹt ở ngày 2026-09-05
    query = f"""
    SELECT source_url 
    FROM core.macro_policy 
    WHERE source = '{source}'
      AND published_at >= '2026-09-05 00:00:00' 
      AND published_at <= '2026-09-06 23:59:59'
    LIMIT {limit}
    """
    rows = con.execute(query).fetchall()
    urls = [r[0] for r in rows if r[0]]
    logger.info(f"[{source.upper()}] Tìm thấy {len(urls)} bài viết cần sửa ngày.")

    if not urls:
        con.close()
        return 0

    session = requests.Session()
    fixed_records: list[tuple[str, dt.datetime]] = []

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(extract_true_date, u, source, session): u for u in urls}
        for fut in as_completed(futures):
            u, real_date = fut.result()
            if real_date:
                fixed_records.append((u, real_date))
                logger.info(f"  -> [Sửa ngày] {u} ===> {real_date.strftime('%Y-%m-%d %H:%M')}")

    dur = time.time() - t0
    logger.info(f"[{source.upper()}] Đã bóc tách thành công {len(fixed_records)}/{len(urls)} ngày thực tế trong {dur:.2f}s.")

    # Cập nhật hàng loạt vào DuckDB
    if fixed_records:
        df_update = pd.DataFrame(fixed_records, columns=["source_url", "real_published_at"])
        con.register("df_fix", df_update)
        con.execute("""
            UPDATE core.macro_policy
            SET published_at = df_fix.real_published_at,
                available_at = df_fix.real_published_at
            FROM df_fix
            WHERE core.macro_policy.source_url = df_fix.source_url
        """)
        con.unregister("df_fix")
        logger.info(f"[{source.upper()}] Đã cập nhật thành công {len(fixed_records)} bản ghi vào database.")

    con.close()
    return len(fixed_records)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Vá lỗi Selector ngày cho Báo Đầu tư và Thời báo Ngân hàng")
    parser.add_argument("--source", choices=["baodautu", "thoibaonganhang", "all"], default="all", help="Nguồn cần sửa")
    parser.add_argument("--limit", type=int, default=100, help="Số lượng bài viết cần sửa (0 = tất cả)")
    parser.add_argument("--workers", type=int, default=15, help="Số worker song song")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="Đường dẫn file DuckDB")
    args = parser.parse_args()

    lim = 999999 if args.limit <= 0 else args.limit
    sources = ["baodautu", "thoibaonganhang"] if args.source == "all" else [args.source]

    for s in sources:
        fix_dates(db_path=args.db, source=s, limit=lim, workers=args.workers)


if __name__ == "__main__":
    main()
