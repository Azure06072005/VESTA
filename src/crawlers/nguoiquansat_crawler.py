"""Người Quan Sát (nguoiquansat.vn) Financial & Market Commentary Crawler.

File: src/crawlers/nguoiquansat_crawler.py
Mô tả:
    Thu thập các tin tức, bài phân tích chuyên sâu về thị trường chứng khoán,
    dòng tiền, kết quả kinh doanh và bình luận cổ phiếu niêm yết từ nguoiquansat.vn.
    Tuân thủ RFC 9309 và cơ chế Circuit Breaker (dừng ngay khi bị từ chối/reject).
    Chuẩn hóa 11 cột vào staging.macro_policy và core.macro_policy.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger("nguoiquansat_crawler")

BASE_URL = "https://nguoiquansat.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://nguoiquansat.vn/",
}

DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ-CP|NĐ-CP|TT-BTC|TT-NHNN|QĐ-TTg|QĐ-UBCK))\b",
    re.IGNORECASE,
)


def parse_nqs_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày giờ công bố bài viết an toàn."""
    time_tag = soup.find("time") or soup.find(class_=lambda c: c and ("date" in c or "time" in c))
    search_text = time_tag.get_text(strip=True) if time_tag else text
    m = DATE_PATTERN.search(search_text)
    if m:
        try:
            d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mth <= 12 and 1 <= d <= 31:
                return dt.datetime(y, mth, d, 8, 0, 0, tzinfo=dt.timezone.utc)
        except Exception:
            pass
    return dt.datetime.now(dt.timezone.utc)


def parse_nqs_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết Người Quan Sát chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 15:
        return None

    published_at = parse_nqs_date(soup, html[:2000])
    paras = [
        p.get_text(strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 35 and not p.find_parent("footer")
    ]
    body = "\n\n".join(paras)
    if len(body) < 50:
        body = headline

    summary = paras[0][:400] if paras else headline[:400]
    doc_nums = list(set(DOC_NUMBER_PATTERN.findall(body + " " + headline)))
    doc_number = doc_nums[0] if doc_nums else None
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "nguoiquansat",
        "issuing_body": "Người Quan Sát (Nguoiquansat.vn)",
        "doc_type": "EQUITY_COMMENTARY",
        "doc_number": doc_number,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline[:500],
        "summary": summary,
        "body": body,
        "source_url": url,
        "fetched_at": now,
    }


def write_macro_policy(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Lưu bài viết vào staging và core theo chuẩn 11 cột."""
    if df.empty:
        return 0

    required_cols = [
        "source", "issuing_body", "doc_type", "doc_number",
        "published_at", "available_at", "headline", "summary", "body",
        "source_url", "fetched_at"
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    con.register("df_nqs_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_nqs_staging")
    con.unregister("df_nqs_staging")

    con.register("df_nqs_core", df[required_cols])
    res = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_nqs_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n = res.fetchall()[0][0] if res else len(df)
    con.unregister("df_nqs_core")
    return n


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải danh sách URL đã có để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'nguoiquansat'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_nguoiquansat_crawler(
    max_days: int = 5,
    max_articles: int = 50,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy quy trình cào Người Quan Sát với Circuit Breaker."""
    session = requests.Session()
    session.headers.update(HEADERS)

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_urls(con)

    try:
        resp = session.get("https://nguoiquansat.vn/sitemap.xml", timeout=12)
        if resp.status_code in (401, 403, 410, 429, 503):
            logger.warning(f"[CIRCUIT BREAKER] nguoiquansat.vn từ chối yêu cầu (HTTP {resp.status_code}).")
            con.close()
            return {"status": "rejected", "http_status": resp.status_code, "total_written": 0}
        resp.raise_for_status()
        daily_sitemaps = [
            u for u in re.findall(r"<loc>(.*?)</loc>", resp.text)
            if "sitemap-article-" in u
        ][:max_days]
    except Exception as e:
        logger.warning(f"[CIRCUIT BREAKER] Lỗi kết nối nguoiquansat sitemap: {e}. Bỏ qua site.")
        con.close()
        return {"status": "rejected", "error": str(e), "total_written": 0}

    total_written = 0
    breaker_tripped = False

    for sitemap_url in daily_sitemaps:
        if breaker_tripped:
            break
        try:
            s_resp = session.get(sitemap_url, timeout=12)
            if s_resp.status_code in (401, 403, 410, 429, 503):
                logger.warning(f"[CIRCUIT BREAKER] nguoiquansat từ chối sitemap con (HTTP {s_resp.status_code}).")
                break
            if s_resp.status_code != 200:
                continue

            urls = [
                u for u in re.findall(r"<loc>(.*?)</loc>", s_resp.text)
                if u not in existing_urls and u.endswith(".html")
            ]
        except Exception as e:
            logger.warning(f"[CIRCUIT BREAKER] Lỗi sitemap {sitemap_url}: {e}")
            break

        records = []
        for url in urls:
            time.sleep(delay_seconds)
            try:
                art_resp = session.get(url, timeout=12)
                if art_resp.status_code in (401, 403, 410, 429, 503):
                    logger.warning(f"[CIRCUIT BREAKER] nguoiquansat từ chối bài viết (HTTP {art_resp.status_code}).")
                    breaker_tripped = True
                    break
                if art_resp.status_code == 200:
                    rec = parse_nqs_article(art_resp.text, url)
                    if rec:
                        records.append(rec)
                        existing_urls.add(url)
            except Exception as e:
                logger.warning(f"[CIRCUIT BREAKER] Lỗi bài {url}: {e}")
                breaker_tripped = True
                break

            if max_articles and total_written + len(records) >= max_articles:
                breaker_tripped = True
                break

        if records:
            n = write_macro_policy(con, pd.DataFrame(records))
            total_written += n
            logger.info(f"-> [nguoiquansat] Đã ghi nhận +{n} bài phân tích mới.")

    con.close()
    return {
        "status": "success" if not breaker_tripped else "partial_success",
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Nguoi Quan Sat Crawler")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="DuckDB path")
    parser.add_argument("--max-articles", type=int, default=20, help="Số bài tối đa")
    args = parser.parse_args()

    res = run_nguoiquansat_crawler(db_path=args.db, max_articles=args.max_articles)
    print("\n=== Nguoi Quan Sat Crawler Complete ===")
    for k, v in res.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
