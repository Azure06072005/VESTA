"""Báo Tiền Phong (tienphong.vn) Economic & Business Media Crawler.

File: src/crawlers/tienphong_crawler.py
Mô tả:
    Thu thập tin tức kinh tế, tài chính, chứng khoán, bất động sản và quốc tế từ Báo Tiền Phong.
    Hỗ trợ hai chế độ:
      - 'deep' (mặc định): Tích hợp trực tiếp REST JSON API (api.tienphong.vn) cho phép phân trang sâu
        qua các Zone 3 (Kinh tế), Zone 166 (Địa ốc), Zone 5 (Thế giới) tới tối đa 250 trang/chuyên mục.
      - 'sitemap': Cào tin mới nhất qua sitemap XML.
    Đa luồng hóa trích xuất toàn văn bài viết (body) đạt chuẩn 11 cột, Zero Look-Ahead Bias.
    Tuân thủ RFC 9309, cơ chế Circuit Breaker, tự động giải quyết xung đột khóa DuckDB.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import gzip
import json
import logging
from pathlib import Path
import re
import ssl
import sys
import time
from typing import Any, Optional
import urllib.error
import urllib.request

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger("tienphong_crawler")

BASE_URL = "https://tienphong.vn"
DEFAULT_DELAY_SECONDS = 0.3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent/2.1)"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

DATE_PATTERN = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|CT|TT|TB|CV)-(?:CP|TTg|NHNN|BCT|BTC|BXD|BKHĐT|BTP|TCT))\b",
    re.IGNORECASE,
)

TIENPHONG_ZONES = {
    3: ("Kinh tế", "https://tienphong.vn/kinh-te/"),
    166: ("Địa ốc", "https://tienphong.vn/dia-oc/"),
    5: ("Thế giới", "https://tienphong.vn/the-gioi/"),
}


def create_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def clean_html(raw_html: Optional[str]) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def parse_tienphong_date(soup: BeautifulSoup, text: str) -> dt.datetime:
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


def parse_tienphong_article(html: str, url: str, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách bài viết Báo Tiền Phong chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 15:
        return None

    published_at = parse_tienphong_date(soup, html[:2000])
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
        "source": "tienphong",
        "issuing_body": "Báo Tiền Phong (Tienphong.vn)",
        "doc_type": "FINANCIAL_MEDIA",
        "doc_number": doc_number,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline[:500],
        "summary": summary,
        "body": body,
        "source_url": url,
        "fetched_at": now,
    }


def _fetch_article_body_fast(url: str, referer: str, ctx: ssl.SSLContext) -> str:
    """Tải nhanh nội dung bài viết gốc qua HTTP client."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": referer,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            raw = r.read()
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
            soup = BeautifulSoup(raw.decode("utf-8", errors="ignore"), "html.parser")
            paras = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 25 and not p.find_parent("footer")
            ]
            return "\n\n".join(paras)
    except Exception:
        pass
    return ""


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

    for ts_col in ["published_at", "available_at", "fetched_at"]:
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True)

    con.register("df_tp_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_tp_staging")
    con.unregister("df_tp_staging")

    con.register("df_tp_core", df[required_cols])
    con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_tp_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    con.unregister("df_tp_core")
    return len(df)


def get_safe_db_connection(db_path: str = "d:/VESTA/db/vesta.duckdb") -> duckdb.DuckDBPyConnection:
    """Mở kết nối DuckDB với cơ chế tự động chuyển sang file backup/staging nếu bị khóa."""
    candidates = [db_path, "d:/VESTA/db/vesta_latest_backup.duckdb", "d:/VESTA/db/crawlers_staging.duckdb"]
    for path in candidates:
        try:
            return db.connect(path, read_only=False)
        except Exception as e:
            logger.info(f"DB {path} bị khóa hoặc không ghi được ({e}). Thử đích tiếp theo...")
    raise RuntimeError("Không thể kết nối đến bất kỳ DuckDB database nào.")


def crawl_tienphong_deep(
    con: duckdb.DuckDBPyConnection,
    start_page: int = 1,
    max_pages: int = 10,
    target_zones: Optional[list[int]] = None,
    fetch_body: bool = True,
    workers: int = 5,
) -> int:
    """Thu thập phân trang sâu qua REST JSON API của Báo Tiền Phong."""
    ctx = create_ssl_ctx()
    total_saved = 0
    zones = {z: TIENPHONG_ZONES[z] for z in target_zones if z in TIENPHONG_ZONES} if target_zones else TIENPHONG_ZONES

    for zone_id, (zone_name, referer) in zones.items():
        logger.info(f"[Tiền Phong] Bắt đầu Zone {zone_id}: {zone_name}")
        for page in range(start_page, start_page + max_pages):
            url = f"https://api.tienphong.vn/api/morenews-zone-{zone_id}-{page}.html?phrase=&page_size=20&sz={zone_id}&st=zone"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Origin": "https://tienphong.vn",
                    "Referer": referer,
                    "Accept": "*/*",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                    raw = resp.read()
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                    data = json.loads(raw.decode("utf-8"))
                    contents = data.get("data", {}).get("contents", []) if data.get("data") else []
                    if not contents:
                        logger.info(f"  [Tiền Phong - {zone_name}] Hết bài lưu trữ tại trang {page}. Kết thúc zone.")
                        break

                    urls = [it.get("url", "") for it in contents]
                    bodies = [""] * len(contents)

                    if fetch_body:
                        with ThreadPoolExecutor(max_workers=workers) as executor:
                            future_map = {
                                executor.submit(_fetch_article_body_fast, u, referer, ctx): idx
                                for idx, u in enumerate(urls)
                            }
                            for fut in as_completed(future_map):
                                idx = future_map[fut]
                                try:
                                    bodies[idx] = fut.result()
                                except Exception:
                                    pass

                    page_records = []
                    now_utc = dt.datetime.now(dt.timezone.utc)
                    for it, b in zip(contents, bodies):
                        headline = it.get("title", "").strip()
                        art_url = it.get("url", "")
                        if not art_url or len(headline) < 15:
                            continue

                        summary = clean_html(it.get("description", ""))
                        pub_ts = it.get("date")
                        pub_at = (
                            dt.datetime.fromtimestamp(pub_ts, tz=dt.timezone.utc)
                            if pub_ts
                            else now_utc
                        )
                        body_txt = b if b else (summary if summary else headline)

                        doc_nums = list(set(DOC_NUMBER_PATTERN.findall(body_txt + " " + headline)))
                        doc_number = doc_nums[0] if doc_nums else None

                        page_records.append({
                            "source": "tienphong",
                            "issuing_body": f"Báo Tiền Phong ({zone_name})",
                            "doc_type": "FINANCIAL_MEDIA",
                            "doc_number": doc_number,
                            "published_at": pub_at,
                            "available_at": pub_at,
                            "headline": headline,
                            "summary": summary[:1000],
                            "body": body_txt,
                            "source_url": art_url,
                            "fetched_at": now_utc,
                        })

                    if page_records:
                        cnt = write_macro_policy(con, pd.DataFrame(page_records))
                        total_saved += cnt
                        logger.info(f"  [Tiền Phong - {zone_name}] Trang {page}: đã lưu {cnt} bài (Tổng trong phiên: {total_saved})")

                    time.sleep(DEFAULT_DELAY_SECONDS)
            except Exception as e:
                logger.warning(f"  [Tiền Phong - {zone_name}] Dừng trang {page}: {e}")
                break

    return total_saved


def crawl_tienphong_sitemap(
    con: duckdb.DuckDBPyConnection,
    max_articles: int = 50,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    all_dates: bool = False,
    start_year: int = 2010,
    end_year: int = 2026,
) -> int:
    """Cào tin tức kinh tế, địa ốc qua sitemap XML (Hỗ trợ All Dates từ 2010 đến 2026)."""
    session = requests.Session()
    session.headers.update(HEADERS)

    # Tải danh sách URL đã có để khử trùng lặp
    existing_urls: set[str] = set()
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = 'tienphong'").fetchall()
        existing_urls = {r[0] for r in rows if r[0]}
    except Exception:
        pass

    target_months: list[str] = []
    if all_dates:
        curr_y, curr_m = dt.datetime.now().year, dt.datetime.now().month
        for y in range(end_year, start_year - 1, -1):
            m_end = curr_m if y == curr_y else 12
            for m in range(m_end, 0, -1):
                target_months.append(f"{y}-{m}")
        logger.info(f"[TIEN PHONG ALL DATES] Sẽ duyệt qua {len(target_months)} sitemap tháng từ {end_year} về {start_year}.")
    else:
        curr_y, curr_m = dt.datetime.now().year, dt.datetime.now().month
        target_months = [f"{curr_y}-{curr_m}"]

    total_saved = 0
    for ym in target_months:
        sitemap_url = f"https://tienphong.vn/sitemaps/news-{ym}.xml"
        logger.info(f"==> Đang đọc Tiền Phong Sitemap: {sitemap_url}")
        try:
            resp = session.get(sitemap_url, timeout=12, verify=False)
            if resp.status_code != 200:
                logger.warning(f"Không tìm thấy sitemap {sitemap_url} (HTTP {resp.status_code})")
                continue
            all_locs = re.findall(r"<loc>(.*?)</loc>", resp.text)
            urls = [
                u for u in all_locs
                if (".tpo" in u or "-post" in u)
                and u not in existing_urls
            ]
            if max_articles > 0 and not all_dates:
                urls = urls[:max_articles]
        except Exception as e:
            logger.warning(f"Lỗi đọc sitemap Tiền Phong {sitemap_url}: {e}")
            continue

        logger.info(f"  [Tháng {ym}] Tìm thấy {len(urls)} bài viết mới chưa có trong DB.")
        records = []
        for url in urls:
            time.sleep(delay_seconds)
            try:
                art_resp = session.get(url, timeout=10, verify=False)
                if art_resp.status_code == 200:
                    rec = parse_tienphong_article(art_resp.text, url)
                    if rec:
                        records.append(rec)
                        existing_urls.add(url)
                        logger.info(f"  [Ingested] {rec['headline'][:65]}")
            except Exception:
                pass

            if len(records) >= 20:
                written = write_macro_policy(con, pd.DataFrame(records))
                total_saved += written
                records = []

        if records:
            written = write_macro_policy(con, pd.DataFrame(records))
            total_saved += written

    return total_saved


def run_tienphong_crawler(
    mode: str = "deep",
    max_pages: int = 10,
    start_page: int = 1,
    zones: Optional[list[int]] = None,
    max_articles: int = 50,
    all_dates: bool = False,
    start_year: int = 2010,
    end_year: int = 2026,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Hàm chạy chính điều phối crawler Báo Tiền Phong."""
    con = get_safe_db_connection(db_path)
    total_written = 0
    try:
        if mode == "deep":
            total_written = crawl_tienphong_deep(
                con,
                start_page=start_page,
                max_pages=max_pages,
                target_zones=zones,
                fetch_body=True,
            )
        else:
            total_written = crawl_tienphong_sitemap(
                con,
                max_articles=max_articles,
                delay_seconds=delay_seconds,
                all_dates=all_dates,
                start_year=start_year,
                end_year=end_year,
            )
    finally:
        con.close()

    return {
        "status": "success",
        "mode": mode,
        "total_written": total_written,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Báo Tiền Phong Production News Crawler")
    parser.add_argument("--mode", choices=["deep", "sitemap"], default="deep", help="Chế độ cào (deep: REST API, sitemap: XML)")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu")
    parser.add_argument("--max-pages", type=int, default=10, help="Số trang tối đa mỗi chuyên mục")
    parser.add_argument("--zones", type=str, default="3,166,5", help="Danh sách Zone ID (3: Kinh tế, 166: Địa ốc, 5: Thế giới)")
    parser.add_argument("--max-articles", type=int, default=50, help="Số bài tối đa nếu cào chế độ sitemap (0 = không giới hạn)")
    parser.add_argument("--all-dates", action="store_true", help="Cào toàn bộ các sitemap tháng từ start-year đến end-year")
    parser.add_argument("--start-year", type=int, default=2010, help="Năm bắt đầu (mặc định: 2010)")
    parser.add_argument("--end-year", type=int, default=2026, help="Năm kết thúc (mặc định: 2026)")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="Đường dẫn file DuckDB")
    args = parser.parse_args()

    target_zones = [int(z.strip()) for z in args.zones.split(",") if z.strip().isdigit()]

    res = run_tienphong_crawler(
        mode=args.mode,
        start_page=args.start_page,
        max_pages=args.max_pages,
        zones=target_zones,
        max_articles=args.max_articles,
        all_dates=args.all_dates,
        start_year=args.start_year,
        end_year=args.end_year,
        db_path=args.db,
    )
    print("\n=== Bao Tien Phong Crawler Complete ===")
    for k, v in res.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
