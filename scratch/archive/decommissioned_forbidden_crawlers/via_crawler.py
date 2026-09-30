"""Hiệp hội Internet Việt Nam (via.org.vn) Crawler.

File: src/crawlers/via_crawler.py
Mô tả:
    Thu thập tin tức chính sách AI, dữ liệu số, viễn thông, chuyển đổi số quốc gia
    từ via.org.vn (liên quan FPT, CMG, FOX, CTR, ELC).
    Tuân thủ RFC 9309 và cơ chế Circuit Breaker.
    Lưu trữ chuẩn 11 cột vào staging.macro_policy và core.macro_policy.
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

logger = logging.getLogger("via_crawler")

BASE_URL = "https://via.org.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_via_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày công bố bài viết VIA."""
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


def parse_via_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết VIA chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")
    # On VIA, h1 is often the logo banner, fallback_title carries the article title
    headline = fallback_title
    if not headline or len(headline) < 15:
        h1 = soup.find("h1") or soup.find("h2")
        if h1 and len(h1.get_text(strip=True)) > 15:
            headline = h1.get_text(strip=True)

    if not headline or len(headline) < 15:
        return None

    published_at = parse_via_date(soup, html[:2000])
    paras = [
        p.get_text(strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 25 and not p.find_parent("footer")
    ]
    body = "\n\n".join(paras)
    if len(body) < 50:
        body = headline

    summary = paras[0][:400] if paras else headline[:400]
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "via",
        "issuing_body": "Hiệp hội Internet Việt Nam (VIA)",
        "doc_type": "TELECOM_INTERNET",
        "doc_number": None,
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

    con.register("df_via_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_via_staging")
    con.unregister("df_via_staging")

    con.register("df_via_core", df[required_cols])
    res = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_via_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n = res.fetchall()[0][0] if res else len(df)
    con.unregister("df_via_core")
    return n


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL đã có để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'via'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_via_crawler(
    max_articles: int = 20,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy quy trình cào VIA với Circuit Breaker."""
    session = requests.Session()
    session.headers.update(HEADERS)

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_urls(con)

    cat_url = "https://via.org.vn/Tin-Chinh-sach"
    try:
        resp = session.get(cat_url, timeout=12, verify=False)
        if resp.status_code in (401, 403, 410, 429, 503):
            logger.warning(f"[CIRCUIT BREAKER] via.org.vn từ chối (HTTP {resp.status_code}).")
            con.close()
            return {"status": "rejected", "http_status": resp.status_code, "total_written": 0}
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a["href"].strip()
            if len(title) > 25 and not any(x in href for x in ["facebook.com", "web30s.vn", "#"]):
                # Clean up nested domain bug if present
                if "https://via.org.vn/https://via.org.vn/" in href:
                    href = href.replace("https://via.org.vn/https://via.org.vn/", "https://via.org.vn/")
                full = urljoin(BASE_URL, href)
                if full not in [it["url"] for it in items] and full not in existing_urls:
                    items.append({"title": title, "url": full})
        candidate_items = items[:max_articles]
    except Exception as e:
        logger.warning(f"[CIRCUIT BREAKER] Lỗi kết nối via.org.vn: {e}. Bỏ qua.")
        con.close()
        return {"status": "rejected", "error": str(e), "total_written": 0}

    records = []
    breaker_tripped = False

    for it in candidate_items:
        time.sleep(delay_seconds)
        try:
            art_resp = session.get(it["url"], timeout=12, verify=False)
            if art_resp.status_code in (401, 403, 410, 429, 503):
                logger.warning(f"[CIRCUIT BREAKER] via từ chối bài viết (HTTP {art_resp.status_code}). Dừng.")
                breaker_tripped = True
                break
            if art_resp.status_code == 200:
                rec = parse_via_article(art_resp.text, it["url"], fallback_title=it["title"])
                if rec:
                    records.append(rec)
                    existing_urls.add(it["url"])
        except Exception as e:
            logger.warning(f"[CIRCUIT BREAKER] Lỗi bài {it['url']}: {e}")
            breaker_tripped = True
            break

    total_written = 0
    if records:
        total_written = write_macro_policy(con, pd.DataFrame(records))
        logger.info(f"-> [via] Đã lưu +{total_written} bài viết Internet VIA.")

    con.close()
    return {
        "status": "success" if not breaker_tripped else "partial_success",
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="VIA Crawler")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="DuckDB path")
    parser.add_argument("--max-articles", type=int, default=10, help="Số bài tối đa")
    args = parser.parse_args()

    res = run_via_crawler(db_path=args.db, max_articles=args.max_articles)
    print("\n=== VIA Crawler Complete ===")
    for k, v in res.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
