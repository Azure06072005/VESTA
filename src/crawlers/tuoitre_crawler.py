"""Báo Tuổi Trẻ (tuoitre.vn) Macro & Business News Crawler.

File: src/crawlers/tuoitre_crawler.py
Mô tả:
    Thu thập tin tức kinh doanh, tài chính, chứng khoán, bất động sản, thế giới và thời sự vĩ mô từ Báo Tuổi Trẻ.
    Hỗ trợ hai chế độ:
      - 'deep' (mặc định): Tích hợp luồng phân trang dòng thời gian (timeline stream: tuoitre.vn/timeline/{zone}/trang-{page}.htm)
        cho phép truy xuất ngược thời gian tới năm 2009 (hơn 4.000 trang lưu trữ).
        Trích xuất ngày giờ chuẩn hóa ISO-8601 UTC từ thẻ <meta property="article:published_time">, loại bỏ triệt để Look-Ahead Bias.
      - 'rss': Cào tin mới nhất qua kênh RSS https://tuoitre.vn/rss/kinh-doanh.rss (chế độ fallback).
    Đa luồng hóa trích xuất nội dung toàn văn (8 workers) chuẩn 11 cột, cơ chế thử lại chống gián đoạn mạng.
    Tự động xử lý khóa file DuckDB (fallback vesta_latest_backup.duckdb).
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
from email.utils import parsedate_to_datetime
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

logger = logging.getLogger("tuoitre_crawler")

BASE_URL = "https://tuoitre.vn"
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

TUOITRE_ZONES = {
    11: "Kinh doanh",
    89: "Bất động sản",
    10: "Thế giới",
    3: "Thời sự",
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


def parse_tuoitre_date(pub_date_str: str, soup: BeautifulSoup) -> dt.datetime:
    """Trích xuất ngày công bố bài viết Tuổi Trẻ với độ ưu tiên thẻ meta ISO-8601."""
    meta_pub = soup.find("meta", property="article:published_time") or soup.find("meta", property="og:updated_time")
    if meta_pub and meta_pub.get("content"):
        try:
            return pd.to_datetime(meta_pub["content"], utc=True).to_pydatetime()
        except Exception:
            pass

    if pub_date_str:
        try:
            return parsedate_to_datetime(pub_date_str).astimezone(dt.timezone.utc)
        except Exception:
            pass

    time_tag = soup.find(class_=lambda c: c and ("date" in c or "time" in c))
    search_text = time_tag.get_text(strip=True) if time_tag else ""
    m = DATE_PATTERN.search(search_text)
    if m:
        try:
            d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mth <= 12 and 1 <= d <= 31:
                return dt.datetime(y, mth, d, 8, 0, 0, tzinfo=dt.timezone.utc)
        except Exception:
            pass
    return dt.datetime.now(dt.timezone.utc)


def parse_tuoitre_article(
    html: str,
    url: str,
    fallback_title: str = "",
    pub_date_str: str = "",
) -> dict[str, Any] | None:
    """Bóc tách bài viết Tuổi Trẻ chuẩn 11 cột."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1") or soup.find(class_=lambda c: c and "title" in c)
    headline = h1.get_text(strip=True) if h1 else fallback_title
    if not headline or len(headline) < 15:
        return None

    published_at = parse_tuoitre_date(pub_date_str, soup)
    paras = [
        p.get_text(strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 25 and not p.find_parent("footer")
    ]
    body = "\n\n".join(paras)
    if len(body) < 50:
        body = headline

    summary = paras[0][:400] if paras else headline[:400]
    doc_nums = list(set(DOC_NUMBER_PATTERN.findall(body + " " + headline)))
    doc_number = doc_nums[0] if doc_nums else None
    now = dt.datetime.now(dt.timezone.utc)

    return {
        "source": "tuoitre",
        "issuing_body": "Báo Tuổi Trẻ (Tuoitre.vn)",
        "doc_type": "GENERAL_NEWS",
        "doc_number": doc_number,
        "published_at": published_at,
        "available_at": published_at,
        "headline": headline[:500],
        "summary": summary,
        "body": body,
        "source_url": url,
        "fetched_at": now,
    }


def _fetch_tuoitre_detail_fast(url: str, ctx: ssl.SSLContext) -> tuple[str, Optional[dt.datetime]]:
    """Tải nhanh chi tiết bài viết Tuổi Trẻ kèm bóc tách thời gian UTC chuẩn."""
    if not url:
        return "", None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            soup = BeautifulSoup(r.read().decode("utf-8", errors="ignore"), "html.parser")
            pub_at = None
            meta_pub = soup.find("meta", property="article:published_time") or soup.find("meta", property="og:updated_time")
            if meta_pub and meta_pub.get("content"):
                try:
                    pub_at = pd.to_datetime(meta_pub["content"], utc=True).to_pydatetime()
                except Exception:
                    pass

            if not pub_at:
                date_el = soup.find(class_=lambda c: c and ("date" in c or "time" in c))
                if date_el:
                    dm = DATE_PATTERN.search(date_el.get_text())
                    if dm:
                        d, m, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                        if 1 <= m <= 12 and 1 <= d <= 31:
                            pub_at = dt.datetime(y, m, d, 8, 0, tzinfo=dt.timezone.utc)

            paras = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 25 and not p.find_parent("footer")
            ]
            return "\n\n".join(paras), pub_at
    except Exception:
        pass
    return "", None


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

    con.register("df_tt_staging", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_tt_staging")
    con.unregister("df_tt_staging")

    con.register("df_tt_core", df[required_cols])
    con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_tt_core
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    con.unregister("df_tt_core")
    return len(df)


def get_safe_db_connection(db_path: str = "d:/VESTA/db/vesta.duckdb") -> duckdb.DuckDBPyConnection:
    """Mở kết nối DuckDB an toàn, tự động fallback sang backup/staging nếu có khóa ghi."""
    candidates = [db_path, "d:/VESTA/db/vesta_latest_backup.duckdb", "d:/VESTA/db/crawlers_staging.duckdb"]
    for path in candidates:
        try:
            return db.connect(path, read_only=False)
        except Exception as e:
            logger.info(f"DB {path} bị khóa hoặc không ghi được ({e}). Thử đích tiếp theo...")
    raise RuntimeError("Không thể kết nối đến bất kỳ DuckDB database nào.")


def crawl_tuoitre_deep(
    con: duckdb.DuckDBPyConnection,
    start_page: int = 1,
    max_pages: int = 10,
    target_zones: Optional[list[int]] = None,
    fetch_body: bool = True,
    workers: int = 8,
) -> int:
    """Thu thập phân trang dòng thời gian sâu của Báo Tuổi Trẻ."""
    ctx = create_ssl_ctx()
    total_saved = 0
    zones = {z: TUOITRE_ZONES[z] for z in target_zones if z in TUOITRE_ZONES} if target_zones else TUOITRE_ZONES

    for zone_id, zone_name in zones.items():
        logger.info(f"[Tuổi Trẻ] Bắt đầu Zone {zone_id}: {zone_name}")
        consecutive_empty = 0
        for page in range(start_page, start_page + max_pages):
            url = f"https://tuoitre.vn/timeline/{zone_id}/trang-{page}.htm"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                resp_html = None
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                            resp_html = resp.read().decode("utf-8", errors="ignore")
                            break
                    except urllib.error.HTTPError as he:
                        if he.code == 404:
                            break
                        time.sleep(1.0 * (attempt + 1))
                    except Exception:
                        time.sleep(1.0 * (attempt + 1))

                if not resp_html:
                    consecutive_empty += 1
                    if consecutive_empty >= 4:
                        logger.info(f"  [Tuổi Trẻ - {zone_name}] Đạt điểm cuối lưu trữ tại trang {page}. Dừng zone.")
                        break
                    continue

                soup = BeautifulSoup(resp_html, "html.parser")
                items = soup.select(".box-category-item, li")
                if not items:
                    consecutive_empty += 1
                    if consecutive_empty >= 4:
                        logger.info(f"  [Tuổi Trẻ - {zone_name}] Hết bài lưu trữ tại trang {page}. Dừng zone.")
                        break
                    continue

                consecutive_empty = 0
                links_and_items = []
                for it in items:
                    a_title = it.find("a", class_=lambda c: c and "title" in c) or it.find("a")
                    if not a_title:
                        continue
                    headline = a_title.get_text(strip=True)
                    rel_href = a_title.get("href", "")
                    if len(headline) < 20 or not rel_href.endswith(".htm") or "/video/" in rel_href:
                        continue
                    full_url = f"https://tuoitre.vn{rel_href}" if rel_href.startswith("/") else rel_href
                    sapo_el = it.find(class_=lambda c: c and "sapo" in c)
                    summary = sapo_el.get_text(strip=True) if sapo_el else headline
                    links_and_items.append((full_url, headline, summary))

                if not links_and_items:
                    continue

                details = [("", None)] * len(links_and_items)
                if fetch_body:
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        future_map = {
                            executor.submit(_fetch_tuoitre_detail_fast, item[0], ctx): idx
                            for idx, item in enumerate(links_and_items)
                        }
                        for fut in as_completed(future_map):
                            idx = future_map[fut]
                            try:
                                details[idx] = fut.result()
                            except Exception:
                                pass

                page_records = []
                now_utc = dt.datetime.now(dt.timezone.utc)
                for (f_url, h, s), (body_txt, p_date) in zip(links_and_items, details):
                    b = body_txt if body_txt else s
                    pub_at = p_date if p_date else now_utc
                    doc_nums = list(set(DOC_NUMBER_PATTERN.findall(b + " " + h)))
                    doc_number = doc_nums[0] if doc_nums else None

                    page_records.append({
                        "source": "tuoitre",
                        "issuing_body": f"Báo Tuổi Trẻ ({zone_name})",
                        "doc_type": "GENERAL_NEWS",
                        "doc_number": doc_number,
                        "published_at": pub_at,
                        "available_at": pub_at,
                        "headline": h,
                        "summary": s[:1000],
                        "body": b,
                        "source_url": f_url,
                        "fetched_at": now_utc,
                    })

                if page_records:
                    cnt = write_macro_policy(con, pd.DataFrame(page_records))
                    total_saved += cnt
                    logger.info(f"  [Tuổi Trẻ - {zone_name}] Trang {page}: đã lưu {cnt} bài (Tổng: {total_saved})")

                time.sleep(DEFAULT_DELAY_SECONDS)
            except Exception as e:
                logger.warning(f"  [Tuổi Trẻ - {zone_name}] Lỗi trang {page}: {e}")
                consecutive_empty += 1
                if consecutive_empty >= 4:
                    break

    return total_saved


def crawl_tuoitre_rss(
    con: duckdb.DuckDBPyConnection,
    max_articles: int = 50,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
) -> int:
    """Cào tin mới nhất qua RSS (chế độ fallback)."""
    session = requests.Session()
    session.headers.update(HEADERS)

    rss_url = "https://tuoitre.vn/rss/kinh-doanh.rss"
    try:
        resp = session.get(rss_url, timeout=12)
        if resp.status_code != 200:
            return 0
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []
        for it in soup.find_all("item"):
            t_node = it.find("title")
            l_node = it.find("link")
            p_node = it.find("pubdate")
            title = t_node.get_text(strip=True) if t_node else ""
            link = ""
            if l_node:
                link = l_node.next_sibling.strip() if l_node.next_sibling else l_node.get_text(strip=True)
            if not link and it.find("guid"):
                link = it.find("guid").get_text(strip=True)
            pub_date = p_node.get_text(strip=True) if p_node else ""
            if link:
                items.append({"title": title, "url": link, "pub_date": pub_date})
        items = items[:max_articles]
    except Exception as e:
        logger.warning(f"Lỗi đọc RSS Tuổi Trẻ: {e}")
        return 0

    records = []
    for item in items:
        time.sleep(delay_seconds)
        try:
            art_resp = session.get(item["url"], timeout=10)
            if art_resp.status_code == 200:
                rec = parse_tuoitre_article(
                    art_resp.text,
                    item["url"],
                    fallback_title=item["title"],
                    pub_date_str=item["pub_date"],
                )
                if rec:
                    records.append(rec)
        except Exception:
            pass

    return write_macro_policy(con, pd.DataFrame(records)) if records else 0


def run_tuoitre_crawler(
    mode: str = "deep",
    max_pages: int = 10,
    start_page: int = 1,
    zones: Optional[list[int]] = None,
    max_articles: int = 50,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    db_path: str = "d:/VESTA/db/vesta.duckdb",
) -> dict[str, Any]:
    """Hàm điều phối chạy crawler Báo Tuổi Trẻ."""
    con = get_safe_db_connection(db_path)
    total_written = 0
    try:
        if mode == "deep":
            total_written = crawl_tuoitre_deep(
                con,
                start_page=start_page,
                max_pages=max_pages,
                target_zones=zones,
                fetch_body=True,
            )
        else:
            total_written = crawl_tuoitre_rss(
                con,
                max_articles=max_articles,
                delay_seconds=delay_seconds,
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

    parser = argparse.ArgumentParser(description="Báo Tuổi Trẻ Production News Crawler")
    parser.add_argument("--mode", choices=["deep", "rss"], default="deep", help="Chế độ cào (deep: timeline phân trang, rss: RSS)")
    parser.add_argument("--start-page", type=int, default=1, help="Trang bắt đầu")
    parser.add_argument("--max-pages", type=int, default=10, help="Số trang tối đa mỗi chuyên mục")
    parser.add_argument("--zones", type=str, default="11,89", help="Danh sách Zone ID (11: Kinh doanh, 89: Bất động sản, 10: Thế giới, 3: Thời sự)")
    parser.add_argument("--max-articles", type=int, default=50, help="Số bài tối đa nếu cào chế độ rss")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="Đường dẫn file DuckDB")
    args = parser.parse_args()

    target_zones = [int(z.strip()) for z in args.zones.split(",") if z.strip().isdigit()]

    res = run_tuoitre_crawler(
        mode=args.mode,
        start_page=args.start_page,
        max_pages=args.max_pages,
        zones=target_zones,
        max_articles=args.max_articles,
        db_path=args.db,
    )
    print("\n=== Bao Tuoi Tre Crawler Complete ===")
    for k, v in res.items():
        print(f"  {k:20s}: {v}")


if __name__ == "__main__":
    main()
