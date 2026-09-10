"""VESTA High-Speed Deep Crawler for Reverse-Engineered Portals.

High-throughput, concurrent detail harvesting for:
1. Bộ Tài chính (MOF): REST API (/api/article/reads & /api/article/getbyslug)
2. Báo Tiền Phong: REST API (api.tienphong.vn/api/morenews-zone-{zone}-{page}.html)
3. Báo Tuổi Trẻ: Timeline stream (/timeline/{zone}/trang-{page}.htm)
4. VietnamFinance: AJAX stream (/loadmoreiframe/actloadcateajax-cate{id}-page{page}-date{date}/)

Idempotent persistence into DuckDB `staging.macro_policy` and `core.macro_policy`.
Zero look-ahead bias: `available_at >= published_at`.
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
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from bs4 import BeautifulSoup
import duckdb
import pandas as pd

# Workspace root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("deep_portal_crawler")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent/2.1)"
)

DATE_REGEX = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")
DOC_NUM_REGEX = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|CT|TT|TB|CV)-(?:CP|TTg|NHNN|BCT|BTC|BXD|BKHĐT|BTP|TCT))\b",
    re.IGNORECASE,
)


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


def get_db_connection(custom_path: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    if custom_path:
        return db.connect(custom_path)
    try:
        return db.connect()
    except duckdb.IOException:
        backup = "db/vesta_latest_backup.duckdb"
        logger.info(f"Default vesta.duckdb locked. Connecting to {backup}")
        return db.connect(backup)


def save_to_macro_policy(con: duckdb.DuckDBPyConnection, records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    df = pd.DataFrame(records)
    required_cols = [
        "source", "issuing_body", "doc_type", "doc_number",
        "published_at", "available_at", "headline", "summary",
        "body", "source_url", "fetched_at"
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    for ts_col in ["published_at", "available_at", "fetched_at"]:
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True)

    # Staging
    con.register("df_staging_deep", df[required_cols])
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_staging_deep")
    con.unregister("df_staging_deep")

    # Core idempotent
    con.register("df_core_deep", df[required_cols])
    con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_core_deep
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    con.unregister("df_core_deep")
    return len(df)


# =====================================================================
# 1. BỘ TÀI CHÍNH (MOF) CRAWLER (CONCURRENT DETAIL FETCHING)
# =====================================================================
MOF_CATEGORIES = {
    "tin-tuc-su-kien-8": "f0d30405-0417-46a5-9dd0-fd1472428c57",
    "thoi-su": "63661983-10cb-458c-b835-76d8c1276450",
    "tai-chinh-trong-nuoc": "2fa020f0-83e7-4aa7-afa5-189687a4f1cb",
    "nghien-cuu-trao-doi-4": "25a336ea-06f2-4e37-a0ad-ff470a1ce941",
    "tin-chinh-sach-tai-chinh": "38ccd03f-ccaf-4e4d-9319-b90df2207feb",
    "hoat-dong-nganh-tai-chinh": "34c5a20a-5c6b-4012-89e7-65d718ea31dc",
    "thi-truong-tai-chinh": "9d96ccc0-1a88-4887-98e1-d11c3e2c956a",
    "tai-chinh-phap-luat": "85139ab2-de82-45ab-8de8-eda3004285fd",
    "chi-dao-dieu-hanh-1": "227618ab-3f56-4eed-8b8f-7589893fb863",
    "tai-chinh-quoc-te": "29fa2fdf-d806-4732-9058-08dd333794fb",
    "tieu-diem": "1b595c9b-e6e1-4e25-9fed-ed54e2761c23",
    "thong-cao-bao-chi-2": "5760ab6b-0e52-47e8-937e-62525c66a877",
}


def _fetch_mof_detail(slug: str, ctx: ssl.SSLContext) -> str:
    if not slug:
        return ""
    try:
        url = f"https://www.mof.gov.vn/api/article/getbyslug?slug={slug}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.mof.gov.vn/"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") and isinstance(data.get("data"), dict):
                return clean_html(data["data"].get("articleContent", ""))
    except Exception:
        pass
    return ""


def crawl_mof(con: duckdb.DuckDBPyConnection, max_pages: int = 10, page_size: int = 40, fetch_body: bool = True, start_page: int = 0) -> int:
    logger.info(f"=== [MOF] Starting deep crawl: pages {start_page} to {start_page + max_pages}, page_size={page_size} ===")
    ctx = create_ssl_ctx()
    total_saved = 0

    for cat_name, cat_id in MOF_CATEGORIES.items():
        logger.info(f"[MOF] Category: {cat_name}")
        for page in range(start_page, start_page + max_pages):
            offset = page * page_size
            url = f"https://www.mof.gov.vn/api/article/reads?offset={offset}&limit={page_size}"
            req = urllib.request.Request(
                url,
                data=json.dumps({"categoryId": cat_id}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                    "Origin": "https://www.mof.gov.vn",
                    "Referer": "https://www.mof.gov.vn/",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("data", [])
                    if not items:
                        break

                    slugs = [it.get("slug") or "" for it in items]
                    bodies = [""] * len(items)

                    # Concurrent detail fetching with ThreadPoolExecutor
                    if fetch_body:
                        with ThreadPoolExecutor(max_workers=6) as executor:
                            future_map = {executor.submit(_fetch_mof_detail, slug, ctx): idx for idx, slug in enumerate(slugs)}
                            for fut in as_completed(future_map):
                                idx = future_map[fut]
                                try:
                                    bodies[idx] = fut.result()
                                except Exception:
                                    pass

                    page_records = []
                    for it, b in zip(items, bodies):
                        slug = it.get("slug") or ""
                        source_url = f"https://www.mof.gov.vn/webcenter/portal/btcvn/pages_r/l/tin-bo-tai-chinh?dDocName={slug}" if slug else f"mof://{it.get('id')}"
                        headline = it.get("title", "").strip()
                        summary = it.get("description", "") or ""
                        body = b if b else (summary if summary else headline)

                        pub_str = it.get("publicationTime")
                        pub_at = dt.datetime.now(dt.timezone.utc)
                        if pub_str:
                            try:
                                pub_at = dt.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                            except Exception:
                                pass

                        doc_m = DOC_NUM_REGEX.search(headline + " " + body[:500])
                        doc_num = doc_m.group(1).upper() if doc_m else None

                        page_records.append({
                            "source": "mof",
                            "issuing_body": "Bộ Tài chính",
                            "doc_type": "Thông tin & Chính sách Tài chính",
                            "doc_number": doc_num,
                            "published_at": pub_at,
                            "available_at": pub_at,
                            "headline": headline,
                            "summary": summary[:1000],
                            "body": body,
                            "source_url": source_url,
                            "fetched_at": dt.datetime.now(dt.timezone.utc),
                        })

                    if page_records:
                        cnt = save_to_macro_policy(con, page_records)
                        total_saved += cnt
                        logger.info(f"  [MOF - {cat_name}] Page {page+1}: fetched & saved {cnt} items (Total in run: {total_saved})")

                    time.sleep(0.3)
            except Exception as e:
                logger.warning(f"  [MOF - {cat_name}] Error on page {page+1}: {e}")
                break

    return total_saved


# =====================================================================
# 2. BÁO TIỀN PHONG CRAWLER (CONCURRENT DETAIL FETCHING)
# =====================================================================
TIENPHONG_ZONES = {
    3: ("Kinh tế", "https://tienphong.vn/kinh-te/"),
    166: ("Địa ốc", "https://tienphong.vn/dia-oc/"),
    5: ("Thế giới", "https://tienphong.vn/the-gioi/"),
}


def _fetch_tienphong_detail(url: str, referer: str, ctx: ssl.SSLContext) -> str:
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": referer})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            raw = r.read()
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
            soup = BeautifulSoup(raw.decode("utf-8", errors="ignore"), "html.parser")
            paras = [
                p.get_text(strip=True) for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 25 and not p.find_parent("footer")
            ]
            return "\n\n".join(paras)
    except Exception:
        pass
    return ""


def crawl_tienphong(con: duckdb.DuckDBPyConnection, max_pages: int = 15, fetch_body: bool = True, start_page: int = 1) -> int:
    logger.info(f"=== [Tiền Phong] Starting deep JSON API crawl: pages {start_page} to {start_page + max_pages - 1} ===")
    ctx = create_ssl_ctx()
    total_saved = 0

    for zone_id, (zone_name, referer) in TIENPHONG_ZONES.items():
        logger.info(f"[Tiền Phong] Zone {zone_id}: {zone_name}")
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
                    contents = data.get("data", {}).get("contents", [])
                    if not contents:
                        break

                    urls = [it.get("url", "") for it in contents]
                    bodies = [""] * len(contents)

                    # Concurrent detail fetching
                    if fetch_body:
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            future_map = {executor.submit(_fetch_tienphong_detail, u, referer, ctx): idx for idx, u in enumerate(urls)}
                            for fut in as_completed(future_map):
                                idx = future_map[fut]
                                try:
                                    bodies[idx] = fut.result()
                                except Exception:
                                    pass

                    page_records = []
                    for it, b in zip(contents, bodies):
                        headline = it.get("title", "").strip()
                        art_url = it.get("url", "")
                        if not art_url or len(headline) < 15:
                            continue

                        summary = clean_html(it.get("description", ""))
                        pub_ts = it.get("date")
                        pub_at = dt.datetime.fromtimestamp(pub_ts, tz=dt.timezone.utc) if pub_ts else dt.datetime.now(dt.timezone.utc)
                        body = b if b else (summary if summary else headline)

                        page_records.append({
                            "source": "tienphong",
                            "issuing_body": f"Báo Tiền Phong ({zone_name})",
                            "doc_type": "Kinh tế & Thị trường",
                            "doc_number": None,
                            "published_at": pub_at,
                            "available_at": pub_at,
                            "headline": headline,
                            "summary": summary[:1000],
                            "body": body,
                            "source_url": art_url,
                            "fetched_at": dt.datetime.now(dt.timezone.utc),
                        })

                    if page_records:
                        cnt = save_to_macro_policy(con, page_records)
                        total_saved += cnt
                        logger.info(f"  [Tiền Phong - {zone_name}] Page {page}: fetched & saved {cnt} articles (Total: {total_saved})")

                    time.sleep(0.3)
            except Exception as e:
                logger.warning(f"  [Tiền Phong - {zone_name}] Error on page {page}: {e}")
                break

    return total_saved


# =====================================================================
# 3. BÁO TUỔI TRẺ CRAWLER (TIMELINE PAGINATION)
# =====================================================================
TUOITRE_ZONES = {
    11: "Kinh doanh",
    89: "Bất động sản",
    10: "Thế giới",
    3: "Thời sự",
}


def _fetch_tuoitre_detail(url: str, ctx: ssl.SSLContext) -> tuple[str, Optional[dt.datetime]]:
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
                    dm = DATE_REGEX.search(date_el.get_text())
                    if dm:
                        d, m, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                        if 1 <= m <= 12 and 1 <= d <= 31:
                            pub_at = dt.datetime(y, m, d, 8, 0, tzinfo=dt.timezone.utc)
            paras = [
                p.get_text(strip=True) for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 25 and not p.find_parent("footer")
            ]
            return "\n\n".join(paras), pub_at
    except Exception:
        pass
    return "", None


def crawl_tuoitre(con: duckdb.DuckDBPyConnection, max_pages: int = 15, fetch_body: bool = True, start_page: int = 1, target_zones: Optional[list[int]] = None) -> int:
    logger.info(f"=== [Tuổi Trẻ] Starting deep timeline crawl: pages {start_page} to {start_page + max_pages - 1} ===")
    ctx = create_ssl_ctx()
    total_saved = 0

    zones_to_crawl = {z: TUOITRE_ZONES[z] for z in target_zones if z in TUOITRE_ZONES} if target_zones else TUOITRE_ZONES

    for zone_id, zone_name in zones_to_crawl.items():
        logger.info(f"[Tuổi Trẻ] Zone {zone_id}: {zone_name}")
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
                        logger.info(f"  [Tuổi Trẻ - {zone_name}] Reached end of archive at page {page} (consecutive empty pages). Stopping zone.")
                        break
                    continue

                soup = BeautifulSoup(resp_html, "html.parser")
                items = soup.select(".box-category-item, li")
                if not items:
                    consecutive_empty += 1
                    if consecutive_empty >= 4:
                        logger.info(f"  [Tuổi Trẻ - {zone_name}] Reached end of archive at page {page} (no items found). Stopping zone.")
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

                # Concurrent detail fetching (8 workers for higher throughput)
                details = [("", None)] * len(links_and_items)
                if fetch_body:
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        future_map = {executor.submit(_fetch_tuoitre_detail, item[0], ctx): idx for idx, item in enumerate(links_and_items)}
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
                    page_records.append({
                        "source": "tuoitre",
                        "issuing_body": f"Báo Tuổi Trẻ ({zone_name})",
                        "doc_type": "Tài chính & Kinh doanh",
                        "doc_number": None,
                        "published_at": pub_at,
                        "available_at": pub_at,
                        "headline": h,
                        "summary": s[:1000],
                        "body": b,
                        "source_url": f_url,
                        "fetched_at": now_utc,
                    })

                if page_records:
                    cnt = save_to_macro_policy(con, page_records)
                    total_saved += cnt
                    logger.info(f"  [Tuổi Trẻ - {zone_name}] Page {page}: fetched & saved {cnt} articles (Total: {total_saved})")

                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"  [Tuổi Trẻ - {zone_name}] Error on page {page}: {e}")
                consecutive_empty += 1
                if consecutive_empty >= 4:
                    break

    return total_saved


# =====================================================================
# 4. VIETNAMFINANCE CRAWLER
# =====================================================================
VNF_CATEGORIES = {
    2: ("Tài chính - Ngân hàng", "https://vietnamfinance.vn/tai-chinh/"),
    3: ("Bất động sản & Quy hoạch", "https://vietnamfinance.vn/bat-dong-san/"),
    5: ("Đầu tư & Thị trường", "https://vietnamfinance.vn/dau-tu/"),
}


def _fetch_vnf_detail(url: str, referer: str, ctx: ssl.SSLContext) -> tuple[str, Optional[dt.datetime]]:
    if not url:
        return "", None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": referer})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            soup = BeautifulSoup(r.read().decode("utf-8", errors="ignore"), "html.parser")
            pub_at = None
            time_el = soup.find(class_=lambda c: c and ("date" in c or "time" in c))
            if time_el:
                dm = DATE_REGEX.search(time_el.get_text())
                if dm:
                    d, m, y = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
                    if 1 <= m <= 12 and 1 <= d <= 31:
                        pub_at = dt.datetime(y, m, d, 8, 0, tzinfo=dt.timezone.utc)
            paras = [
                p.get_text(strip=True) for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 25 and not p.find_parent("footer")
            ]
            return "\n\n".join(paras), pub_at
    except Exception:
        pass
    return "", None


def crawl_vietnamfinance(con: duckdb.DuckDBPyConnection, max_pages: int = 15, fetch_body: bool = True, start_page: int = 1) -> int:
    logger.info(f"=== [VietnamFinance] Starting deep AJAX crawl: pages {start_page} to {start_page + max_pages - 1} ===")
    ctx = create_ssl_ctx()
    total_saved = 0
    today_str = dt.datetime.now().strftime("%Y-%m-%d-08-00-00")

    for cate_id, (cate_name, referer) in VNF_CATEGORIES.items():
        logger.info(f"[VietnamFinance] Category {cate_id}: {cate_name}")
        for page in range(start_page, start_page + max_pages):
            url = f"https://vietnamfinance.vn/loadmoreiframe/actloadcateajax-cate{cate_id}-page{page}-date{today_str}/"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": referer,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                    soup = BeautifulSoup(resp.read().decode("utf-8", errors="ignore"), "html.parser")
                    a_links = [a for a in soup.find_all("a", href=True) if "-d" in a.get("href", "") and a.get("href", "").endswith(".html")]
                    if not a_links:
                        break

                    seen_in_page = set()
                    links = []
                    for a in a_links:
                        art_url = a.get("href", "").strip()
                        if not art_url.startswith("http"):
                            art_url = f"https://vietnamfinance.vn{art_url}"
                        headline = a.get_text(strip=True)
                        if art_url in seen_in_page or len(headline) < 18:
                            continue
                        seen_in_page.add(art_url)
                        links.append((art_url, headline))

                    details = [("", None)] * len(links)
                    if fetch_body:
                        with ThreadPoolExecutor(max_workers=5) as executor:
                            future_map = {executor.submit(_fetch_vnf_detail, l[0], referer, ctx): idx for idx, l in enumerate(links)}
                            for fut in as_completed(future_map):
                                idx = future_map[fut]
                                try:
                                    details[idx] = fut.result()
                                except Exception:
                                    pass

                    page_records = []
                    now_utc = dt.datetime.now(dt.timezone.utc)
                    for (art_url, headline), (body_txt, p_date) in zip(links, details):
                        b = body_txt if body_txt else headline
                        pub_at = p_date if p_date else now_utc
                        page_records.append({
                            "source": "vietnamfinance",
                            "issuing_body": f"VietnamFinance ({cate_name})",
                            "doc_type": "Tài chính & Đầu tư",
                            "doc_number": None,
                            "published_at": pub_at,
                            "available_at": pub_at,
                            "headline": headline,
                            "summary": headline[:1000],
                            "body": b,
                            "source_url": art_url,
                            "fetched_at": now_utc,
                        })

                    if page_records:
                        cnt = save_to_macro_policy(con, page_records)
                        total_saved += cnt
                        logger.info(f"  [VietnamFinance - {cate_name}] Page {page}: fetched & saved {cnt} articles (Total: {total_saved})")

                    time.sleep(0.3)
            except Exception as e:
                logger.warning(f"  [VietnamFinance - {cate_name}] Error on page {page}: {e}")
                break

    return total_saved


def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA High-Speed Deep Portal Crawler")
    parser.add_argument("--portal", choices=["all", "mof", "tuoitre", "tienphong", "vietnamfinance"], default="all")
    parser.add_argument("--max-pages", type=int, default=10, help="Pages to crawl per category/zone")
    parser.add_argument("--start-page", type=int, default=0, help="Starting page/offset index")
    parser.add_argument("--page-size", type=int, default=40, help="Page size for MOF REST API")
    parser.add_argument("--no-body", action="store_true", help="Skip body fetching for faster crawling")
    parser.add_argument("--zones", type=str, default=None, help="Comma-separated zone IDs to crawl (e.g. 11,89)")
    parser.add_argument("--db", type=str, default=None, help="Target DuckDB database path")
    args = parser.parse_args()

    target_zones = [int(z.strip()) for z in args.zones.split(",") if z.strip().isdigit()] if args.zones else None

    con = get_db_connection(args.db)
    fetch_body = not args.no_body
    start_time = time.time()
    grand_total = 0

    logger.info(f"Initiating high-speed deep crawl for portal: {args.portal.upper()}")

    if args.portal in ("all", "mof"):
        grand_total += crawl_mof(con, max_pages=args.max_pages, page_size=args.page_size, fetch_body=fetch_body, start_page=args.start_page)

    if args.portal in ("all", "tienphong"):
        grand_total += crawl_tienphong(con, max_pages=args.max_pages, fetch_body=fetch_body, start_page=max(1, args.start_page))

    if args.portal in ("all", "tuoitre"):
        grand_total += crawl_tuoitre(con, max_pages=args.max_pages, fetch_body=fetch_body, start_page=max(1, args.start_page), target_zones=target_zones)

    if args.portal in ("all", "vietnamfinance"):
        grand_total += crawl_vietnamfinance(con, max_pages=args.max_pages, fetch_body=fetch_body, start_page=max(1, args.start_page))

    con.close()
    elapsed = time.time() - start_time
    logger.info(f"HIGH-SPEED DEEP CRAWL FINISHED: {grand_total} records written in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    main()
