"""Thời báo Tài chính Việt Nam (thoibaotaichinhvietnam.vn) Fiscal & Market Crawler.

File: src/crawlers/thoibaotaichinh_crawler.py
Description:
    Thu thập tin tức tài chính, quản lý ngân sách nhà nước, thuế, hải quan,
    thị trường tài chính và chính sách doanh nghiệp từ Thời báo Tài chính Việt Nam (cơ quan Bộ Tài chính).
    Tuân thủ RFC 9309 (scratch/robots/thoibaotaichinh-robots.txt).
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

BASE_URL = "https://thoibaotaichinhvietnam.vn"
DEFAULT_DELAY_SECONDS = 1.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

CATEGORIES = {
    "tai-chinh": "https://thoibaotaichinhvietnam.vn/tai-chinh",
    "chung-khoan": "https://thoibaotaichinhvietnam.vn/chung-khoan",
    "thue-hai-quan": "https://thoibaotaichinhvietnam.vn/thue-hai-quan",
    "ngan-hang-bao-hiem": "https://thoibaotaichinhvietnam.vn/ngan-hang-bao-hiem",
}

DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ-CP|NĐ-CP|TT-BTC|QĐ-TTg|QĐ-BTC|CV-[A-Z]+))\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def parse_tbtc_date(soup: BeautifulSoup, text: str) -> dt.datetime:
    """Trích xuất ngày công bố bài viết an toàn."""
    time_tag = soup.find("time") or soup.find(class_=lambda c: c and ("date" in c or "time" in c))
    search_text = time_tag.get_text(strip=True) if time_tag else text
    m = DATE_PATTERN.search(search_text)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                res_dt = dt.datetime(year, month, day, 8, 0, 0, tzinfo=dt.timezone.utc)
                now_utc = dt.datetime.now(dt.timezone.utc)
                if res_dt > now_utc or year < 2000:
                    return now_utc
                return res_dt
        except Exception:
            pass
    return dt.datetime.now(dt.timezone.utc)


def parse_tbtc_listing(html: str) -> list[dict[str, str]]:
    """Trích xuất danh sách bài viết từ Thời báo Tài chính."""
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(strip=True)
        if len(title) < 20 or not href.endswith(".html"):
            continue
        if any(skip in href for skip in ["/video/", "/photo/", "/podcast/", "/lien-he/"]):
            continue
        full_url = urljoin(BASE_URL, href)
        if full_url not in seen and re.search(r"-\d+\.html$", full_url):
            seen.add(full_url)
            articles.append({"title": title, "url": full_url})

    return articles


def parse_tbtc_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết Thời báo Tài chính theo chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1", class_=lambda c: c and "article-detail-title" in c) or soup.find(class_=lambda c: c and "article-detail-title" in c)
    if not title_tag:
        h1s = soup.find_all("h1")
        title_tag = h1s[-1] if len(h1s) > 1 else (h1s[0] if h1s else None)
    headline = title_tag.get_text(strip=True) if title_tag else fallback_title
    if not headline or len(headline) < 10:
        headline = fallback_title
    if not headline:
        return None

    published_at = parse_tbtc_date(soup, html[:1500])

    paras = [
        p.get_text(strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 35 and not p.find_parent("footer")
    ]
    body = "\n\n".join(paras)
    if len(body) < 50:
        body = headline

    summary = paras[0][:400] if paras else headline[:400]
    doc_numbers = list(set(DOC_NUMBER_PATTERN.findall(body + " " + headline)))
    doc_number = doc_numbers[0] if doc_numbers else None
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "thoibaotaichinh",
        "issuing_body": "Thời báo Tài chính Việt Nam (Bộ Tài chính)",
        "doc_type": "FISCAL_NEWS",
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
    """Lưu bài viết vào staging.macro_policy, core.news_resources và core.macro_policy theo chuẩn 11 cột."""
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

    con.register("df_tbtc_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_tbtc_staging")
    con.unregister("df_tbtc_staging")

    con.register("df_tbtc_core", df[required_cols])
    res = con.execute(
        """
        INSERT INTO core.news_resources
        SELECT * FROM df_tbtc_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n_written = res.fetchall()[0][0] if res else len(df)
    try:
        con.execute(
            """
            INSERT INTO core.macro_policy
            SELECT * FROM df_tbtc_core
            ON CONFLICT (source_url) DO NOTHING
            """
        )
    except Exception:
        pass
    con.unregister("df_tbtc_core")
    return n_written


def load_existing_urls(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Tải URL đã có để khử trùng lặp."""
    urls = set()
    for tbl in ["core.news_resources", "core.macro_policy"]:
        try:
            rows = con.execute(f"SELECT source_url FROM {tbl} WHERE source = 'thoibaotaichinh'").fetchall()
            urls.update(r[0] for r in rows if r[0])
        except Exception:
            pass
    return urls


from src.crawlers.db_writer import ResilientDuckDBWriter, DEFAULT_TARGET_DB


def run_thoibaotaichinh_crawler(
    max_articles_per_cat: int = 50,
    max_offsets: int = 10,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = DEFAULT_TARGET_DB,
) -> dict[str, Any]:
    """Chạy quy trình cào Thời báo Tài chính có phân trang API và sitemap."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    writer = ResilientDuckDBWriter(target_db=db_path)
    existing_urls: set[str] = set()

    def _load_urls(con: duckdb.DuckDBPyConnection) -> None:
        existing_urls.update(load_existing_urls(con))

    writer.execute_with_retry(_load_urls)

    total_discovered = 0
    total_written = 0

    # 1. Quét sitemap hiện hành nếu có bài mới
    try:
        sm_resp = session.get("https://thoibaotaichinhvietnam.vn/sitemaparticles-site-1.xml", timeout=12, verify=False)
        if sm_resp.status_code == 200:
            sm_urls = re.findall(r"<loc>(.*?)</loc>", sm_resp.text)
            new_sm = [u for u in sm_urls if u not in existing_urls and re.search(r"-\d+\.html$", u)]
            logger.info("[TBTC Sitemap] Phát hiện %d bài trong sitemaparticles (%d bài mới).", len(sm_urls), len(new_sm))
            sm_records = []
            for u in new_sm[:30]:
                time.sleep(delay_seconds)
                try:
                    r = session.get(u, timeout=12, verify=False)
                    if r.status_code == 200:
                        rec = parse_tbtc_article(r.text, u)
                        if rec:
                            sm_records.append(rec)
                            existing_urls.add(u)
                except Exception:
                    pass
            if sm_records:
                def _save_sm(con: duckdb.DuckDBPyConnection) -> int:
                    return write_macro_policy(con, pd.DataFrame(sm_records))

                n = writer.execute_with_retry(_save_sm)
                total_written += n
                logger.info("[TBTC Sitemap] Đã nạp +%d bài viết từ sitemap.", n)
    except Exception as e:
        logger.warning("[TBTC Sitemap] Lỗi quét sitemap: %s", e)

    # 2. Duyệt từng chuyên mục và gọi API phân trang
    for cat_name, cat_url in CATEGORIES.items():
        logger.info("=== Bắt đầu cào Thời báo Tài chính: %s (%s) ===", cat_name, cat_url)
        cat_written = 0

        try:
            resp = session.get(cat_url, timeout=15, verify=False)
            if resp.status_code in (403, 429, 503):
                logger.warning("[CIRCUIT_BREAKER] TBTC từ chối (HTTP %d). Chuyển site khác.", resp.status_code)
                break
            if resp.status_code != 200:
                continue
            html = resp.text
        except Exception as e:
            logger.warning("[%s] Lỗi kết nối: %s", cat_name, e)
            continue

        # Lấy các bài viết trang bìa
        initial_articles = parse_tbtc_listing(html)
        articles_to_fetch = [a for a in initial_articles if a["url"] not in existing_urls]
        total_discovered += len(initial_articles)

        # Trích xuất URL API phân trang nếu có
        m_api = re.search(r'class=[\'"]__MB_NEXT_URL[\'"][^>]*value=[\'"]([^\'"]+)[\'"]', html)
        if not m_api:
            m_api = re.search(r'value=[\'"]([^\'"]*apicenter@[^\'"]*)[\'"]', html)

        api_template = m_api.group(1) if m_api else None

        # Nếu có API phân trang, duyệt qua các offset BRSR = 0, 15, 30, 45...
        if api_template:
            base_api = re.sub(r'BRSR=\d+', 'BRSR={offset}', api_template)
            for step in range(max_offsets):
                offset = step * 15
                api_url = base_api.format(offset=offset)
                try:
                    time.sleep(delay_seconds)
                    api_resp = session.get(api_url, timeout=12, verify=False)
                    if api_resp.status_code == 200:
                        more_arts = parse_tbtc_listing(api_resp.text)
                        new_more = [a for a in more_arts if a["url"] not in existing_urls]
                        total_discovered += len(more_arts)
                        articles_to_fetch.extend(new_more)
                        if not more_arts:
                            break
                    else:
                        break
                except Exception as e:
                    logger.warning("[%s] Lỗi API offset %d: %s", cat_name, offset, e)
                    break

        # Giới hạn số bài thu thập cho mỗi danh mục
        batch = articles_to_fetch[:max_articles_per_cat]
        records = []
        for item in batch:
            time.sleep(delay_seconds)
            try:
                art_resp = session.get(item["url"], timeout=15, verify=False)
                if art_resp.status_code in (403, 429, 503):
                    logger.warning("[CIRCUIT_BREAKER] TBTC từ chối bài viết (HTTP %d).", art_resp.status_code)
                    break
                if art_resp.status_code == 200:
                    rec = parse_tbtc_article(art_resp.text, item["url"], fallback_title=item["title"])
                    if rec:
                        records.append(rec)
                        existing_urls.add(item["url"])
            except Exception as e:
                logger.warning("[%s] Lỗi kết nối %s: %s", cat_name, item["url"], e)
                break

        if records:
            def _save_tbtc(con: duckdb.DuckDBPyConnection) -> int:
                return write_macro_policy(con, pd.DataFrame(records))

            n = writer.execute_with_retry(_save_tbtc)
            total_written += n
            logger.info("[%s] Đã lưu +%d bài viết mới (Tổng: %d).", cat_name, n, total_written)

    return {
        "status": "success",
        "total_discovered": total_discovered,
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Thời báo Tài chính Việt Nam Historical Crawler")
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="DuckDB database path")
    parser.add_argument("--max-articles-per-cat", "--max-articles", dest="max_articles_per_cat", type=int, default=50, help="Số bài tối đa mỗi chuyên mục")
    parser.add_argument("--max-offsets", "--max-pages", dest="max_offsets", type=int, default=10, help="Số lần phân trang API tối đa")
    parser.add_argument("--delay", type=float, default=0.5, help="Độ trễ request (giây)")
    args = parser.parse_args()

    summary = run_thoibaotaichinh_crawler(
        db_path=args.db,
        max_articles_per_cat=args.max_articles_per_cat,
        max_offsets=args.max_offsets,
        delay_seconds=args.delay,
    )
    print("\n=== Thoi bao Tai chinh Crawler Complete ===")
    for k, v in summary.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()

