"""Unified Resilient Crawler for Remaining Macro & Financial Sites (VESTA Tier 3).

Combines Group A (Domestic Vietnamese Regulatory & News) and Group B (International Macro Portals).
Implements fail-safe error handling: skips rejected (401/403/Paywall) or unreachable sites,
passes cleanly, and crawls all reachable sources into `staging.macro_policy` and `core.macro_policy`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import ssl
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
import duckdb
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("unified_macro_crawler")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent/2.1)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Detect official document numbers (e.g. 15/2024/TT-BTC, 33/NQ-CP)
DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d+(?:/[0-9]{4})?/(?:NQ|NĐ|QĐ|CT|TT|TB|CV)-(?:CP|TTg|NHNN|BCT|BTC|BXD|BKHĐT|BTP|TCT))\b",
    re.IGNORECASE,
)


def fetch_url(url: str, timeout: int = 10) -> tuple[int, bytes | None, str | None]:
    """Fetch URL content with graceful error capturing.
    
    Returns (status_code, content_bytes, error_message).
    """
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return resp.getcode(), resp.read(), None
    except urllib.error.HTTPError as e:
        return e.code, None, f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return 0, None, f"URL Error: {e.reason}"
    except Exception as e:
        return 0, None, f"Error: {str(e)}"


# =====================================================================
# SITE EXTRACTORS
# =====================================================================

def crawl_yahoo_finance(max_articles: int = 200, all_dates: bool = True) -> list[dict[str, Any]]:
    """Crawls Yahoo Finance macro & equity market news via HAR-derived GraphQL & Activity APIs."""
    logger.info(">>> [YAHOO FINANCE] Khởi chạy cào tin tức tài chính & vĩ mô đa nguồn (GraphQL Topics + Tickers + Search)...")
    try:
        if all_dates:
            from src.crawlers.yahoo_all_dates_crawler import crawl_all_dates_yahoo
            records = crawl_all_dates_yahoo(max_pages_per_topic=3)
        else:
            from src.crawlers.yahoo_finance_crawler import crawl_yahoo_finance as run_yahoo_har
            records = run_yahoo_har(fetch_body=False)
        if records:
            logger.info(f"[YAHOO FINANCE] Đã lấy thành công {len(records)} tin qua HAR API.")
            return records[:max_articles]
    except Exception as e:
        logger.warning(f"[YAHOO FINANCE] Gặp lỗi với HAR API: {e}. Tiếp tục fallback RSS...")

    rss_url = "https://finance.yahoo.com/news/rssindex"
    code, content, err = fetch_url(rss_url, timeout=12)
    if code != 200 or not content:
        logger.warning(f"[YAHOO FINANCE] Bị từ chối hoặc lỗi RSS: {err}. Bỏ qua (PASS).")
        return []

    try:
        root = ET.fromstring(content)
    except Exception as e:
        logger.warning(f"[YAHOO FINANCE] Lỗi phân tích XML RSS: {e}")
        return []

    items = root.findall(".//item")
    records = []
    now = dt.datetime.now(dt.timezone.utc)

    for item in items[:max_articles]:
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        desc_el = item.find("description")

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        summary = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
        
        if not link or not title:
            continue

        published_at = now
        if pub_el is not None and pub_el.text:
            try:
                published_at = pd.to_datetime(pub_el.text, utc=True).to_pydatetime()
            except Exception:
                published_at = now

        art_code, art_content, art_err = fetch_url(link, timeout=8)
        body = summary
        if art_code == 200 and art_content:
            soup = BeautifulSoup(art_content, "html.parser")
            body_div = soup.find("div", class_="body") or soup.find("article")
            if body_div:
                body = body_div.get_text(separator="\n", strip=True)

        records.append({
            "source": "yahoo_finance",
            "issuing_body": "Yahoo Finance / Global Markets",
            "doc_type": "news",
            "doc_number": None,
            "published_at": published_at,
            "available_at": published_at,
            "headline": title,
            "summary": summary[:500] if summary else title,
            "body": body if body else title,
            "source_url": link,
            "fetched_at": now,
        })
        time.sleep(0.3)

    return records


def crawl_moj_gov_vn(max_articles: int = 50) -> list[dict[str, Any]]:
    """Crawls Bộ Tư pháp (moj.gov.vn) legal & policy announcements."""
    logger.info(">>> [BỘ TƯ PHÁP - MOJ] Khởi chạy cào thông tin pháp luật & điều hành...")
    base_url = "https://moj.gov.vn"
    landing_url = "https://moj.gov.vn/portal/tin-tuc/chi-dao-dieu-hanh.html"
    
    code, content, err = fetch_url(landing_url, timeout=10)
    if code != 200 or not content:
        # Fallback to homepage
        code, content, err = fetch_url(base_url, timeout=10)
        if code != 200 or not content:
            logger.warning(f"[MOJ] Bị từ chối hoặc lỗi: {err}. Bỏ qua (PASS).")
            return []

    soup = BeautifulSoup(content, "html.parser")
    article_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/portal/tin-tuc/chi-tiet/" in href or "/chi-dao-dieu-hanh/" in href:
            full_url = href if href.startswith("http") else base_url + href
            article_links.add(full_url)

    logger.info(f"[MOJ] Tìm thấy {len(article_links)} liên kết bài viết.")
    records = []
    now = dt.datetime.now(dt.timezone.utc)

    for url in list(article_links)[:max_articles]:
        art_code, art_content, art_err = fetch_url(url, timeout=8)
        if art_code != 200 or not art_content:
            logger.debug(f"[MOJ] Skip {url}: {art_err}")
            continue

        art_soup = BeautifulSoup(art_content, "html.parser")
        h1 = art_soup.find("h1") or art_soup.find("h2") or art_soup.find("h3")
        headline = h1.get_text(strip=True) if h1 else ""
        if not headline:
            continue

        # Extract body from main tag and paragraph tags
        main_el = art_soup.find("main") or art_soup
        p_tags = [p.get_text().strip() for p in main_el.find_all("p") if len(p.get_text().strip()) > 15]
        body = "\n".join(p_tags)
        if len(body) < 80:
            content_div = (
                art_soup.find("div", class_="news-detail-content")
                or art_soup.find("div", id="content-body")
                or art_soup.find("div", class_="content")
            )
            body = content_div.get_text(separator="\n", strip=True) if content_div else ""
            if len(body) < 80:
                continue

        doc_match = DOC_NUMBER_PATTERN.search(headline + " " + body[:300])
        doc_number = doc_match.group(1) if doc_match else None

        records.append({
            "source": "moj",
            "issuing_body": "Bộ Tư pháp",
            "doc_type": "policy",
            "doc_number": doc_number,
            "published_at": now,
            "available_at": now,
            "headline": headline,
            "summary": body[:300],
            "body": body,
            "source_url": url,
            "fetched_at": now,
        })
        time.sleep(0.4)

    logger.info(f"[MOJ] Thu thập thành công {len(records)} văn bản/bài viết.")
    return records


def crawl_vnanet_vn(max_articles: int = 50) -> list[dict[str, Any]]:
    """Crawls Thông tấn xã Việt Nam (vnanet.vn) economic news."""
    logger.info(">>> [THÔNG TẤN XÃ VIỆT NAM - VNANET] Khởi chạy cào tin kinh tế vĩ mô...")
    base_url = "https://vnanet.vn"
    target_url = "https://vnanet.vn/vi/tin-tuc/kinh-te-13/"
    
    code, content, err = fetch_url(target_url, timeout=12)
    if code != 200 or not content:
        logger.warning(f"[VNANET] Bị từ chối hoặc lỗi: {err}. Bỏ qua (PASS).")
        return []

    soup = BeautifulSoup(content, "html.parser")
    article_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "TrackingView.aspx?IID=" in href:
            full_url = href if href.startswith("http") else base_url + href
            article_links.add(full_url)
        elif "/vi/tin-tuc/kinh-te" in href and href.endswith(".html") and "page" not in href:
            full_url = href if href.startswith("http") else base_url + href
            article_links.add(full_url)

    logger.info(f"[VNANET] Tìm thấy {len(article_links)} liên kết tin kinh tế.")
    records = []
    now = dt.datetime.now(dt.timezone.utc)

    for url in list(article_links)[:max_articles]:
        art_code, art_content, art_err = fetch_url(url, timeout=8)
        if art_code != 200 or not art_content:
            logger.debug(f"[VNANET] Skip {url}: {art_err}")
            continue

        art_soup = BeautifulSoup(art_content, "html.parser")
        h1 = art_soup.find("h1")
        headline = h1.get_text(strip=True) if h1 else ""
        if not headline:
            continue

        body_div = art_soup.find("div", class_="detail-content") or art_soup.find("div", class_="content")
        body = body_div.get_text(separator="\n", strip=True) if body_div else ""

        records.append({
            "source": "vnanet",
            "issuing_body": "Thông tấn xã Việt Nam",
            "doc_type": "news",
            "doc_number": None,
            "published_at": now,
            "available_at": now,
            "headline": headline,
            "summary": body[:300] if body else headline,
            "body": body if body else headline,
            "source_url": url,
            "fetched_at": now,
        })
        time.sleep(0.3)

    logger.info(f"[VNANET] Thu thập thành công {len(records)} bài viết.")
    return records


def crawl_chinhphu_vn(max_articles: int = 50) -> list[dict[str, Any]]:
    """Crawls Cổng Thông tin điện tử Chính phủ (chinhphu.vn) directives & economic topics."""
    logger.info(">>> [CỔNG TTĐT CHÍNH PHỦ - CHINHPHU.VN] Khởi chạy cào tin chỉ đạo kinh tế...")
    base_url = "https://chinhphu.vn"
    code, content, err = fetch_url(base_url, timeout=10)
    if code != 200 or not content:
        logger.warning(f"[CHINHPHU.VN] Bị từ chối hoặc lỗi: {err}. Bỏ qua (PASS).")
        return []

    soup = BeautifulSoup(content, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".htm") and ("kinh-te" in href or "chi-dao" in href or "chu-de" in href or "tin-tuc" in href):
            full_url = href if href.startswith("http") else base_url + href
            links.add(full_url)

    logger.info(f"[CHINHPHU.VN] Tìm thấy {len(links)} liên kết chỉ đạo điều hành.")
    records = []
    now = dt.datetime.now(dt.timezone.utc)

    for url in list(links)[:max_articles]:
        art_code, art_content, art_err = fetch_url(url, timeout=8)
        if art_code != 200 or not art_content:
            continue

        art_soup = BeautifulSoup(art_content, "html.parser")
        h1 = art_soup.find("h1")
        headline = h1.get_text(strip=True) if h1 else ""
        if not headline:
            continue

        body_div = art_soup.find("div", class_="detail-content") or art_soup.find("div", class_="content")
        body = body_div.get_text(separator="\n", strip=True) if body_div else ""
        if len(body) < 80:
            continue

        doc_match = DOC_NUMBER_PATTERN.search(headline + " " + body[:300])
        doc_number = doc_match.group(1) if doc_match else None

        records.append({
            "source": "vietnam_gov",
            "issuing_body": "Cổng Thông tin điện tử Chính phủ",
            "doc_type": "policy",
            "doc_number": doc_number,
            "published_at": now,
            "available_at": now,
            "headline": headline,
            "summary": body[:300],
            "body": body,
            "source_url": url,
            "fetched_at": now,
        })
        time.sleep(0.3)

    logger.info(f"[CHINHPHU.VN] Thu thập thành công {len(records)} bài viết/chỉ đạo.")
    return records


def try_crawl_rejected_site(name: str, url: str) -> None:
    """Tries fetching a rejected site (Bloomberg, Reuters, WSJ, VOV) and cleanly passes on rejection."""
    logger.info(f">>> [{name.upper()}] Thử nghiệm cào: {url}")
    code, content, err = fetch_url(url, timeout=7)
    if code in (401, 403, 429) or err:
        logger.warning(f"[{name.upper()}] Bị chặn/Từ chối truy cập ({err or f'HTTP {code}'}). PASS và tiếp tục trang khác theo yêu cầu.")
        return
    logger.info(f"[{name.upper()}] Phản hồi bất ngờ: HTTP {code}")


# =====================================================================
# DATABASE WRITER
# =====================================================================

def write_to_db(records: list[dict[str, Any]], duckdb_path: str = "d:/VESTA/db/vesta_latest_backup.duckdb") -> int:
    """Idempotently writes crawled records to staging and core macro_policy."""
    if not records:
        return 0

    df = pd.DataFrame(records)
    required_cols = [
        "source",
        "issuing_body",
        "doc_type",
        "doc_number",
        "published_at",
        "available_at",
        "headline",
        "summary",
        "body",
        "source_url",
        "fetched_at",
    ]
    df = df[required_cols]

    con = duckdb.connect(duckdb_path, read_only=False)
    try:
        # Write staging
        con.register("df_staging", df)
        con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_staging")
        con.unregister("df_staging")

        # Write core with deduplication on source_url
        before_count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
        con.register("df_core", df)
        con.execute("""
            INSERT INTO core.macro_policy
            SELECT * FROM df_core
            ON CONFLICT (source_url) DO NOTHING
        """)
        con.unregister("df_core")
        after_count = con.execute("SELECT count(*) FROM core.macro_policy").fetchone()[0]
        new_inserted = after_count - before_count
        logger.info(f"Ghi thành công vào DuckDB: {len(df)} bản ghi staging, {new_inserted} bản ghi core mới (Deduplicated).")
        return new_inserted
    finally:
        con.close()


def run_pipeline() -> dict[str, Any]:
    """Runs the full combined A + B crawl pipeline."""
    print("=========================================================================")
    print(">>> KHỞI CHẠY PIPELINE CÀO KẾT HỢP NHÓM A & B (BỎ QUA TRANG BỊ CHẶN) <<<")
    print("=========================================================================")

    results = {}
    all_new_records = []

    # 1. Thử nghiệm các trang bị chặn đã biết (Reuters, Bloomberg, WSJ, VOV) để kiểm chứng cơ chế PASS
    print("\n--- 1. KIỂM TRA CÁC TRANG BỊ CHẶN (CHECK REJECT & PASS) ---")
    try_crawl_rejected_site("reuters", "https://www.reuters.com/arc/outboundfeeds/sitemap/?outputType=xml")
    try_crawl_rejected_site("bloomberg", "https://www.bloomberg.com/sitemaps/news/2026-9.xml")
    try_crawl_rejected_site("wsj", "https://www.wsj.com/sitemap.xml")
    try_crawl_rejected_site("vov", "https://vov.vn/kinh-te/post1330042.vov")

    # 2. Cào các trang khả dụng trong Nhóm B (Tài chính quốc tế)
    print("\n--- 2. CÀO NHÓM B: TÀI CHÍNH QUỐC TẾ KHẢ DỤNG ---")
    yahoo_records = crawl_yahoo_finance(max_articles=50)
    results["yahoo_finance"] = len(yahoo_records)
    all_new_records.extend(yahoo_records)

    # 3. Cào các trang khả dụng trong Nhóm A (Cơ quan quản lý & Báo chí Việt Nam)
    print("\n--- 3. CÀO NHÓM A: QUẢN LÝ NHÀ NƯỚC & BÁO CHÍ VIỆT NAM ---")
    moj_records = crawl_moj_gov_vn(max_articles=40)
    results["moj"] = len(moj_records)
    all_new_records.extend(moj_records)

    vnanet_records = crawl_vnanet_vn(max_articles=40)
    results["vnanet"] = len(vnanet_records)
    all_new_records.extend(vnanet_records)

    chinhphu_records = crawl_chinhphu_vn(max_articles=40)
    results["vietnam_gov"] = len(chinhphu_records)
    all_new_records.extend(chinhphu_records)

    # 4. Ghi toàn bộ dữ liệu hợp lệ vào Database vesta_latest_backup.duckdb
    print("\n--- 4. GHI DỮ LIỆU VÀO DATABASE MỤC TIÊU ---")
    new_in_core = write_to_db(all_new_records)
    results["core_new_inserted"] = new_in_core
    results["total_fetched"] = len(all_new_records)

    return results


if __name__ == "__main__":
    res = run_pipeline()
    print("\n=========================================================================")
    print(">>> TỔNG KẾT KẾT QUẢ CÀO KẾT HỢP A & B <<<")
    print("=========================================================================")
    for k, v in res.items():
        print(f"  * {k:<25}: {v}")
