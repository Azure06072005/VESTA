"""Hiệp hội Phân bón Việt Nam (VFAEA - vfaea.vn) Fertilizer Industry Crawler.

File: src/crawlers/vfaea_crawler.py
Description:
    Thu thập thông tin thị trường phân bón (Urea, NPK, DAP, Kali),
    giá khí đầu vào sản xuất đạm, và xúc tiến thương mại nông nghiệp từ VFAEA.
    Tác động trực tiếp lên các mã cổ phiếu phân bón:
    DPM, DCM, BFC, LAS, DDV, PSE.
    Tuân thủ RFC 9309 (scratch/robots/vfaea-robots.txt).
    Cơ chế Circuit Breaker: Nếu bị từ chối (403, 429, 503), lập tức dừng và chuyển sang website khác.
    Lưu trữ chuẩn xác vào staging.macro_policy và core.macro_policy (11 cột chuẩn).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import db

logger = logging.getLogger(__name__)

BASE_URL = "https://vfaea.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

CATEGORIES = {
    "tin-tuc-phan-bon": "https://vfaea.vn",
}

FERTILIZER_TICKERS = ["DPM", "DCM", "BFC", "LAS", "DDV", "PSE"]
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_vfaea_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày công bố bài viết VFAEA."""
    time_el = soup.find("time") or soup.find(class_=lambda c: c and ("date" in c or "time" in c))
    search_text = time_el.get_text(strip=True) if time_el else text
    m = DATE_PATTERN.search(search_text)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                return dt.datetime(year, month, day, 8, 0, 0, tzinfo=dt.timezone.utc)
        except Exception:
            pass
    return dt.datetime.now(dt.timezone.utc)


def parse_vfaea_listing(html: str) -> list[dict[str, str]]:
    """Trích xuất danh sách bài viết từ VFAEA."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if len(title) < 20 or not href.startswith("https://vfaea.vn/"):
            continue
        if any(skip in href for skip in ["/gioi-thieu/", "/lien-he/", "/category/", "/tag/", "/wp-content/"]):
            continue
        if href not in seen:
            seen.add(href)
            articles.append({"title": title, "url": href})

    return articles


def parse_vfaea_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết ngành phân bón theo chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 15:
        return None

    published_at = parse_vfaea_date(soup, html[:1500])

    paras = [
        p.get_text(strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 35 and not p.find_parent("footer")
    ]
    body = "\n\n".join(paras)
    if len(body) < 50:
        body = headline

    summary = paras[0][:400] if paras else headline[:400]
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "vfaea",
        "issuing_body": "Hiệp hội Phân bón Việt Nam (VFAEA)",
        "doc_type": "FERTILIZER_INDUSTRY",
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
    """Lưu bài viết vào staging.macro_policy và core.macro_policy theo chuẩn 11 cột."""
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

    con.register("df_vfaea_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_vfaea_staging")
    con.unregister("df_vfaea_staging")

    con.register("df_vfaea_core", df[required_cols])
    result = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_vfaea_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = result.fetchall()[0][0] if result else len(df)
    con.unregister("df_vfaea_core")
    return n_written


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL đã có để khử trùng lặp."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'vfaea'").fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


def run_vfaea_crawler(
    max_articles: int = 5,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Chạy quy trình cào VFAEA với Circuit Breaker khi bị reject."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    con = db.connect(db_path, read_only=False)
    existing_urls = load_existing_urls(con)

    total_discovered = 0
    total_written = 0

    for cat_name, cat_url in CATEGORIES.items():
        logger.info(f"=== Bắt đầu cào VFAEA (Phân bón): {cat_name} ({cat_url}) ===")

        try:
            resp = session.get(cat_url, timeout=15)
            if resp.status_code in (403, 429, 503):
                logger.warning(
                    f"[CIRCUIT_BREAKER] VFAEA từ chối yêu cầu (HTTP {resp.status_code}). "
                    f"Dừng ngay lập tức và chuyển sang website khác."
                )
                con.close()
                return {"status": "rejected", "http_status": resp.status_code, "total_written": total_written}
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning(f"[CIRCUIT_BREAKER] Không thể kết nối VFAEA: {e}. Chuyển sang website khác.")
            con.close()
            return {"status": "rejected", "error": str(e), "total_written": total_written}

        articles = parse_vfaea_listing(html)
        new_articles = [a for a in articles if a["url"] not in existing_urls][:max_articles]
        total_discovered += len(articles)

        records = []
        for item in new_articles:
            time.sleep(delay_seconds)
            try:
                art_resp = session.get(item["url"], timeout=15)
                if art_resp.status_code in (403, 429, 503):
                    logger.warning(
                        f"[CIRCUIT_BREAKER] VFAEA từ chối bài viết (HTTP {art_resp.status_code}). "
                        f"Dừng ngay lập tức."
                    )
                    break
                if art_resp.status_code == 200:
                    rec = parse_vfaea_article(art_resp.text, item["url"], fallback_title=item["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(item["url"])
            except Exception as e:
                logger.warning(f"[CIRCUIT_BREAKER] Lỗi kết nối {item['url']}: {e}. Dừng bài này.")
                break

        if records:
            df = pd.DataFrame(records)
            n = write_macro_policy(con, df)
            total_written += n
            logger.info(f"[{cat_name}] Đã lưu +{n} bài viết ngành phân bón mới.")

    con.close()
    return {
        "status": "success",
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Hiệp hội Phân bón Việt Nam (VFAEA) Crawler")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="DuckDB database path")
    parser.add_argument("--max-articles", type=int, default=5, help="Số bài tối đa cần cào")
    args = parser.parse_args()

    summary = run_vfaea_crawler(db_path=args.db, max_articles=args.max_articles)
    print("\n=== VFAEA Fertilizer Crawler Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
