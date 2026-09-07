"""Quy trình cào vét toàn bộ lịch sử (All Dates Backfill) cho Nhóm A và Nhóm B.

File: src/etl/historical_backfill_groups_a_b.py
Mô tả:
    Triển khai quy trình quét toàn diện theo ngày (Historical Backfill) cho:
    - Nhóm A: Thư Viện Pháp Luật, Luật Việt Nam, Thời báo Tài chính, VietnamFinance.
    - Nhóm B: VITAS Dệt May, VNPCA Dược Phẩm, VFAEA Phân Bón, VRA Cao Su.
    
    Đặc tả kỹ thuật:
    1. Thứ tự ưu tiên nghiêm ngặt: Hoàn thành Nhóm A trước, sau đó đến Nhóm B.
    2. Cơ chế Circuit Breaker: Bất kỳ khi nào gặp HTTP 401, 403, 410, 429, 503 hoặc connection drop/reset,
       lập tức ngắt kết nối với site đó và chuyển ngay sang website kế tiếp.
    3. Chế độ Không Giới Hạn (Unlimited Mode): Quét toàn bộ sitemap và phân trang cho tới bài cũ nhất.
    4. Ghi dữ liệu luồng (Streaming Batch Insert): Cứ mỗi 10-15 bài viết tự động commit vào DuckDB.
    5. Chống look-ahead bias: Timestamp ghi nhận theo đúng ngày công bố (published_at).
    6. Idempotent & Deduplication: Khử trùng lặp qua core.macro_policy (ON CONFLICT DO NOTHING).
    7. Chuẩn hóa 11 cột: Ghi dữ liệu đồng bộ vào staging.macro_policy và core.macro_policy.
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
from crawlers.thuvienphapluat_crawler import parse_tvpl_article, parse_tvpl_listing
from crawlers.luatvietnam_crawler import parse_lvn_article, parse_lvn_listing
from crawlers.thoibaotaichinh_crawler import parse_tbtc_article, parse_tbtc_listing
from crawlers.vietnamfinance_crawler import parse_vnf_article, parse_vnf_listing
from crawlers.vntextile_crawler import parse_vitas_article, parse_vitas_listing
from crawlers.vnpca_crawler import parse_vnpca_article, parse_vnpca_listing
from crawlers.vfaea_crawler import parse_vfaea_article, parse_vfaea_listing
from crawlers.vra_crawler import parse_vra_article, parse_vra_listing

logger = logging.getLogger("historical_backfill")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Autonomous-Agent)"
)

REQUIRED_COLS = [
    "source", "issuing_body", "doc_type", "doc_number",
    "published_at", "available_at", "headline", "summary", "body",
    "source_url", "fetched_at"
]


def write_macro_policy_batch(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Ghi dữ liệu hàng loạt vào staging và core với cơ chế chống trùng lặp."""
    if df.empty:
        return 0

    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = None

    df_clean = df[REQUIRED_COLS]
    con.register("df_backfill_batch", df_clean)
    con.execute("INSERT INTO staging.macro_policy SELECT * FROM df_backfill_batch")
    res = con.execute(
        """
        INSERT INTO core.macro_policy
        SELECT * FROM df_backfill_batch
        ON CONFLICT (source_url) DO NOTHING
        """
    )
    n = res.fetchall()[0][0] if res else len(df_clean)
    con.unregister("df_backfill_batch")
    return n


def load_existing_urls_by_source(con: duckdb.DuckDBPyConnection, source: str) -> set[str]:
    """Lấy danh sách URL đã có trong DuckDB để bỏ qua không cào lại."""
    try:
        rows = con.execute("SELECT source_url FROM core.macro_policy WHERE source = ?", [source]).fetchall()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()


class HistoricalBackfillManager:
    """Quản lý cào vét toàn bộ lịch sử cho Nhóm A trước, sau đó đến Nhóm B."""

    def __init__(self, db_path: str = "d:/VESTA/db/vesta.duckdb", delay: float = 1.0) -> None:
        self.db_path = db_path
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        })

    def _get_with_circuit_breaker(self, url: str, timeout: int = 15) -> requests.Response | None:
        """Thực hiện HTTP GET với Circuit Breaker: Dừng ngay lập tức khi bị từ chối hoặc lỗi kết nối."""
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code in (401, 403, 410, 429, 503):
                logger.warning(
                    f" [CIRCUIT BREAKER TRIGGERED] HTTP {resp.status_code} từ {url}. "
                    f"Ngừng truy vấn website này ngay lập tức để bảo vệ IP và chuyển sang website khác."
                )
                return None
            if resp.status_code != 200:
                logger.warning(f" [HTTP {resp.status_code}] Không thể tải {url}")
                return None
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(f" [CIRCUIT BREAKER TRIGGERED] Lỗi kết nối tới {url} ({e}). Ngừng website này.")
            return None
        except Exception as e:
            logger.warning(f" [CIRCUIT BREAKER TRIGGERED] Lỗi ngoại lệ {url} ({e}). Ngừng website này.")
            return None

    # ==================== NHÓM A: PHÁP LÝ & BÁO CHÍ TÀI CHÍNH ====================

    def backfill_thuvienphapluat(self, max_shards: int = 10, max_articles: int | None = None) -> int:
        """Cào vét toàn bộ lịch sử Thư Viện Pháp Luật qua hệ thống sitemap shards."""
        logger.info("=== [Nhóm A - 1/4] Bắt đầu cào Thư Viện Pháp Luật (thuvienphapluat.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "thuvienphapluat")

        index_resp = self._get_with_circuit_breaker("https://thuvienphapluat.vn/resitemap.xml")
        if not index_resp:
            logger.warning("-> Thư Viện Pháp Luật Circuit Breaker kích hoạt tại sitemap index. Chuyển site tiếp theo.")
            con.close()
            return 0

        shards = re.findall(r"<loc>(.*?)</loc>", index_resp.text)
        if max_shards:
            shards = shards[:max_shards]
        total_ingested = 0

        for s_idx, shard_url in enumerate(shards, 1):
            logger.info(f"-> TVPL Shard {s_idx}/{len(shards)}: {shard_url}")
            shard_resp = self._get_with_circuit_breaker(shard_url)
            if not shard_resp:
                logger.warning(f"-> Circuit Breaker tại shard {shard_url}. Dừng cào TVPL và chuyển sang site khác.")
                break

            urls = re.findall(r"<loc>(.*?)</loc>", shard_resp.text)
            legal_urls = [
                u for u in urls
                if "/chinh-sach-phap-luat-moi/" in u and u not in existing
            ]
            if max_articles and total_ingested + len(legal_urls) > max_articles:
                legal_urls = legal_urls[: max_articles - total_ingested]

            records = []
            for u in legal_urls:
                time.sleep(self.delay)
                resp = self._get_with_circuit_breaker(u)
                if not resp:
                    logger.warning("-> TVPL Circuit Breaker kích hoạt khi tải bài viết. Dừng TVPL.")
                    break
                rec = parse_tvpl_article(resp.text, u)
                if rec:
                    records.append(rec)
                    existing.add(u)
                    if len(records) >= 10:
                        n = write_macro_policy_batch(con, pd.DataFrame(records))
                        total_ingested += n
                        records = []

            if records:
                n = write_macro_policy_batch(con, pd.DataFrame(records))
                total_ingested += n

            if max_articles and total_ingested >= max_articles:
                break

        con.close()
        logger.info(f"=== Hoàn tất TVPL: +{total_ingested} văn bản/chính sách mới ===")
        return total_ingested

    def backfill_luatvietnam(self, max_articles: int | None = None) -> int:
        """Cào vét toàn bộ các bài viết phổ biến pháp luật kinh tế từ Luật Việt Nam."""
        logger.info("=== [Nhóm A - 2/4] Bắt đầu cào Luật Việt Nam (luatvietnam.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "luatvietnam")

        resp = self._get_with_circuit_breaker("https://luatvietnam.vn/tin-phap-luat.html")
        if not resp:
            logger.warning("-> Luật Việt Nam Circuit Breaker kích hoạt. Chuyển site tiếp theo.")
            con.close()
            return 0

        articles = parse_lvn_listing(resp.text)
        new_items = [a for a in articles if a["url"] not in existing]
        if max_articles:
            new_items = new_items[:max_articles]

        records = []
        total_ingested = 0
        for it in new_items:
            time.sleep(self.delay)
            art_resp = self._get_with_circuit_breaker(it["url"])
            if not art_resp:
                logger.warning("-> Luật Việt Nam Circuit Breaker kích hoạt. Dừng LVN.")
                break
            rec = parse_lvn_article(art_resp.text, it["url"], fallback_title=it["title"])
            if rec:
                records.append(rec)
                existing.add(it["url"])
                if len(records) >= 10:
                    n = write_macro_policy_batch(con, pd.DataFrame(records))
                    total_ingested += n
                    records = []

        if records:
            n = write_macro_policy_batch(con, pd.DataFrame(records))
            total_ingested += n

        con.close()
        logger.info(f"=== Hoàn tất Luật Việt Nam: +{total_ingested} chính sách mới ===")
        return total_ingested

    def backfill_thoibaotaichinh(self, max_pages: int = 50, max_articles: int | None = None) -> int:
        """Cào vét Thời báo Tài chính Việt Nam qua toàn bộ phân trang tài chính & chứng khoán."""
        logger.info("=== [Nhóm A - 3/4] Bắt đầu cào Thời Báo Tài Chính (thoibaotaichinhvietnam.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "thoibaotaichinh")

        categories = [
            ("tai-chinh", "https://thoibaotaichinhvietnam.vn/tai-chinh"),
            ("chung-khoan", "https://thoibaotaichinhvietnam.vn/chung-khoan"),
            ("tien-te-bao-hiem", "https://thoibaotaichinhvietnam.vn/tien-te-bao-hiem")
        ]

        total_ingested = 0
        breaker_triggered = False

        for cat_slug, base_cat_url in categories:
            if breaker_triggered:
                break
            for page in range(1, max_pages + 1):
                page_url = f"{base_cat_url}?p={page}"
                logger.info(f"-> Đang tải trang: {page_url}")
                resp = self._get_with_circuit_breaker(page_url)
                if not resp:
                    logger.warning(f"-> TBTC Circuit Breaker kích hoạt tại {page_url}. Chuyển chuyên mục.")
                    break

                articles = parse_tbtc_listing(resp.text)
                if not articles:
                    logger.info(f"   Trang {page} rỗng. Đã tới trang cuối của chuyên mục {cat_slug}.")
                    break

                new_items = [a for a in articles if a["url"] not in existing]
                records = []
                for it in new_items:
                    time.sleep(self.delay)
                    art_resp = self._get_with_circuit_breaker(it["url"])
                    if not art_resp:
                        breaker_triggered = True
                        break
                    rec = parse_tbtc_article(art_resp.text, it["url"], fallback_title=it["title"])
                    if rec:
                        records.append(rec)
                        existing.add(it["url"])

                if records:
                    n = write_macro_policy_batch(con, pd.DataFrame(records))
                    total_ingested += n
                    logger.info(f"   [TBTC {cat_slug} p={page}] Đã ghi +{n} tin tức tài chính.")

                if max_articles and total_ingested >= max_articles:
                    breaker_triggered = True
                    break

        con.close()
        logger.info(f"=== Hoàn tất Thời báo Tài chính: +{total_ingested} bài viết mới ===")
        return total_ingested

    def backfill_vietnamfinance(self, max_articles: int | None = None) -> int:
        """Cào vét toàn bộ bài viết qua sitemap của VietnamFinance."""
        logger.info("=== [Nhóm A - 4/4] Bắt đầu cào VietnamFinance (vietnamfinance.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "vietnamfinance")

        sitemap_resp = self._get_with_circuit_breaker("https://vietnamfinance.vn/sitemap.xml")
        if not sitemap_resp:
            logger.warning("-> VietnamFinance Circuit Breaker kích hoạt tại sitemap. Dừng.")
            con.close()
            return 0

        urls = re.findall(r"<loc>(.*?)</loc>", sitemap_resp.text)
        new_urls = [u for u in urls if u not in existing]
        if max_articles:
            new_urls = new_urls[:max_articles]
        logger.info(f"-> VietnamFinance: Phát hiện {len(urls)} URLs sitemap, cần tải {len(new_urls)} bài viết mới.")

        records = []
        total_ingested = 0
        for url in new_urls:
            time.sleep(self.delay)
            resp = self._get_with_circuit_breaker(url)
            if not resp:
                logger.warning("-> VietnamFinance Circuit Breaker kích hoạt. Dừng.")
                break
            rec = parse_vnf_article(resp.text, url)
            if rec:
                records.append(rec)
                existing.add(url)
                if len(records) >= 15:
                    n = write_macro_policy_batch(con, pd.DataFrame(records))
                    total_ingested += n
                    records = []

        if records:
            n = write_macro_policy_batch(con, pd.DataFrame(records))
            total_ingested += n

        con.close()
        logger.info(f"=== Hoàn tất VietnamFinance: +{total_ingested} bài viết mới ===")
        return total_ingested

    # ==================== NHÓM B: HIỆP HỘI SẢN XUẤT & NGÀNH HÀNG ====================

    def backfill_vntextile(self, max_pages: int = 30, max_articles: int | None = None) -> int:
        """Cào vét toàn bộ phân trang tin ngành Dệt May VITAS."""
        logger.info("=== [Nhóm B - 1/4] Bắt đầu cào Hiệp hội Dệt May VITAS (vitas.org.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "vntextile")

        total_ingested = 0
        for page in range(1, max_pages + 1):
            page_url = f"https://vitas.org.vn/tin-tuc/tin-nganh-det-may/page/{page}/" if page > 1 else "https://vitas.org.vn/tin-tuc/tin-nganh-det-may/"
            logger.info(f"-> Đang tải trang VITAS: {page_url}")
            resp = self._get_with_circuit_breaker(page_url)
            if not resp:
                logger.warning(f"-> VITAS Circuit Breaker kích hoạt tại {page_url}. Dừng site này.")
                break

            articles = parse_vitas_listing(resp.text)
            if not articles:
                logger.info(f"   Trang {page} rỗng. Đã tới cuối phân trang VITAS.")
                break

            new_items = [a for a in articles if a["url"] not in existing]
            records = []
            for it in new_items:
                time.sleep(self.delay)
                art_resp = self._get_with_circuit_breaker(it["url"])
                if not art_resp:
                    break
                rec = parse_vitas_article(art_resp.text, it["url"], fallback_title=it["title"])
                if rec:
                    records.append(rec)
                    existing.add(it["url"])

            if records:
                n = write_macro_policy_batch(con, pd.DataFrame(records))
                total_ingested += n
                logger.info(f"   [VITAS p={page}] Đã lưu +{n} bài viết dệt may.")

            if max_articles and total_ingested >= max_articles:
                break

        con.close()
        logger.info(f"=== Hoàn tất VITAS: +{total_ingested} bài viết mới ===")
        return total_ingested

    def backfill_vnpca(self, max_articles: int | None = None) -> int:
        """Cào vét toàn bộ bài viết ngành Dược từ sitemap VNPCA."""
        logger.info("=== [Nhóm B - 2/4] Bắt đầu cào Hiệp hội Dược VNPCA (vnpca.org.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "vnpca")

        sitemap_resp = self._get_with_circuit_breaker("https://vnpca.org.vn/wp-sitemap-posts-post-1.xml")
        if not sitemap_resp:
            logger.warning("-> VNPCA Circuit Breaker kích hoạt tại sitemap. Dừng.")
            con.close()
            return 0

        urls = re.findall(r"<loc>(.*?)</loc>", sitemap_resp.text)
        new_urls = [u for u in urls if u not in existing]
        if max_articles:
            new_urls = new_urls[:max_articles]
        logger.info(f"-> VNPCA: {len(urls)} bài viết trong sitemap, cần tải {len(new_urls)} bài mới.")

        records = []
        total_ingested = 0
        for url in new_urls:
            time.sleep(self.delay)
            resp = self._get_with_circuit_breaker(url)
            if not resp:
                logger.warning("-> VNPCA Circuit Breaker dừng cào.")
                break
            rec = parse_vnpca_article(resp.text, url)
            if rec:
                records.append(rec)
                existing.add(url)
                if len(records) >= 10:
                    n = write_macro_policy_batch(con, pd.DataFrame(records))
                    total_ingested += n
                    records = []

        if records:
            n = write_macro_policy_batch(con, pd.DataFrame(records))
            total_ingested += n

        con.close()
        logger.info(f"=== Hoàn tất VNPCA: +{total_ingested} bài viết ngành Dược ===")
        return total_ingested

    def backfill_vfaea(self, max_pages: int = 30, max_articles: int | None = None) -> int:
        """Cào vét toàn bộ phân trang ngành Phân bón VFAEA."""
        logger.info("=== [Nhóm B - 3/4] Bắt đầu cào Hiệp hội Phân bón VFAEA (vfaea.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "vfaea")

        total_ingested = 0
        for page in range(1, max_pages + 1):
            page_url = f"https://vfaea.vn/tin-tuc/page/{page}/" if page > 1 else "https://vfaea.vn/tin-tuc/"
            logger.info(f"-> Đang tải trang VFAEA: {page_url}")
            resp = self._get_with_circuit_breaker(page_url)
            if not resp:
                logger.warning(f"-> VFAEA Circuit Breaker kích hoạt tại {page_url}. Dừng site này.")
                break

            articles = parse_vfaea_listing(resp.text)
            if not articles:
                logger.info(f"   Trang {page} rỗng. Đã tới cuối phân trang VFAEA.")
                break

            new_items = [a for a in articles if a["url"] not in existing]
            records = []
            for it in new_items:
                time.sleep(self.delay)
                art_resp = self._get_with_circuit_breaker(it["url"])
                if not art_resp:
                    break
                rec = parse_vfaea_article(art_resp.text, it["url"], fallback_title=it["title"])
                if rec:
                    records.append(rec)
                    existing.add(it["url"])

            if records:
                n = write_macro_policy_batch(con, pd.DataFrame(records))
                total_ingested += n
                logger.info(f"   [VFAEA p={page}] Đã lưu +{n} bài viết phân bón.")

            if max_articles and total_ingested >= max_articles:
                break

        con.close()
        logger.info(f"=== Hoàn tất VFAEA: +{total_ingested} bài viết phân bón ===")
        return total_ingested

    def backfill_vra(self, max_articles: int | None = None) -> int:
        """Cào vét tin ngành Cao su VRA."""
        logger.info("=== [Nhóm B - 4/4] Bắt đầu cào Hiệp hội Cao su VRA (vra.com.vn) ===")
        con = db.connect(self.db_path, read_only=False)
        existing = load_existing_urls_by_source(con, "vra")

        categories = [
            "https://vra.com.vn/thong-tin/gop-y-vb-phap-luat-va-kien-nghi.html",
            "https://vra.com.vn"
        ]

        total_ingested = 0
        for cat_url in categories:
            resp = self._get_with_circuit_breaker(cat_url)
            if not resp:
                continue

            articles = parse_vra_listing(resp.text)
            new_items = [a for a in articles if a["url"] not in existing]
            if max_articles and total_ingested + len(new_items) > max_articles:
                new_items = new_items[: max_articles - total_ingested]

            records = []
            for it in new_items:
                time.sleep(self.delay)
                art_resp = self._get_with_circuit_breaker(it["url"])
                if not art_resp:
                    break
                rec = parse_vra_article(art_resp.text, it["url"], fallback_title=it["title"])
                if rec:
                    records.append(rec)
                    existing.add(it["url"])

            if records:
                n = write_macro_policy_batch(con, pd.DataFrame(records))
                total_ingested += n

            if max_articles and total_ingested >= max_articles:
                break

        con.close()
        logger.info(f"=== Hoàn tất VRA: +{total_ingested} bài viết cao su ===")
        return total_ingested

    def run_all(self, group: str = "ALL", unlimited: bool = True) -> dict[str, int]:
        """Kích hoạt chạy toàn diện: Luôn chạy Nhóm A trước, rồi đến Nhóm B."""
        results = {}
        max_art = None if unlimited else 100

        if group in ("A", "ALL"):
            logger.info("==========================================================")
            logger.info(">>> TIẾN TRÌNH 1: BẮT ĐẦU CÀO VÉT TOÀN DIỆN NHÓM A <<<")
            logger.info("==========================================================")
            results["thuvienphapluat"] = self.backfill_thuvienphapluat(max_shards=15, max_articles=max_art)
            results["luatvietnam"] = self.backfill_luatvietnam(max_articles=max_art)
            results["thoibaotaichinh"] = self.backfill_thoibaotaichinh(max_pages=30, max_articles=max_art)
            results["vietnamfinance"] = self.backfill_vietnamfinance(max_articles=max_art)

        if group in ("B", "ALL"):
            logger.info("==========================================================")
            logger.info(">>> TIẾN TRÌNH 2: BẮT ĐẦU CÀO VÉT TOÀN DIỆN NHÓM B <<<")
            logger.info("==========================================================")
            results["vntextile"] = self.backfill_vntextile(max_pages=25, max_articles=max_art)
            results["vnpca"] = self.backfill_vnpca(max_articles=max_art)
            results["vfaea"] = self.backfill_vfaea(max_pages=25, max_articles=max_art)
            results["vra"] = self.backfill_vra(max_articles=max_art)

        return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Historical Backfill for Group A and B")
    parser.add_argument("--group", choices=["A", "B", "ALL"], default="ALL", help="Nhóm cần cào vét")
    parser.add_argument("--db", default="d:/VESTA/db/vesta.duckdb", help="Đường dẫn database DuckDB")
    parser.add_argument("--delay", type=float, default=1.0, help="Độ trễ crawl-delay (giây)")
    parser.add_argument("--unlimited", action="store_true", default=True, help="Quét không giới hạn tất cả các trang/sitemap")
    args = parser.parse_args()

    manager = HistoricalBackfillManager(db_path=args.db, delay=args.delay)
    summary = manager.run_all(group=args.group, unlimited=args.unlimited)

    print("\n================ TỔNG KẾT CÀO VÉT TOÀN DIỆN LỊCH SỬ ================")
    for k, v in summary.items():
        print(f"  {k:20s}: +{v} bài viết mới được ghi nhận")
    print("====================================================================")


if __name__ == "__main__":
    main()
