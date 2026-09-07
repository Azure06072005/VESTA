"""VESTA Daily Crawler Orchestrator & Multi-Tier Execution Pipeline.

File: src/etl/daily_crawler_orchestrator.py
Description:
    Unified daily crawler runner implementing:
    - Tier 1: vnstock / vnstock_data API crawling (Symbol, OHLCV, News, BCTC, Events, Quotes).
    - Tier 2: CafeF & Vietstock Finance enhancers (CDKT Balance Sheet, Full Article Bodies,
              Broker Research Reports, Market Indices, Foreign Flow Volume).
    - Tier 3: Macro & Sectoral Regulatory News (Baodautu, Baochinhphu, SBV, MOIT, VASEP,
              HoREA, VBA, World Bank, etc., parsed from configs/robots_global.yaml).
    - Watermark-based incremental ingestion with early-stop optimization.
    - Strict RFC 9309 robots.txt compliance and rate-limiting.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

import duckdb
import yaml

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from src.etl import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VESTA.DailyOrchestrator")


class DailyCrawlerOrchestrator:
    """Điều phối và thực thi toàn diện pipeline cào dữ liệu hàng ngày của VESTA."""

    def __init__(self, config_path: str = "configs/robots_global.yaml") -> None:
        self.config_path = Path(config_path)
        if not self.config_path.is_absolute():
            self.config_path = PROJECT_ROOT / self.config_path
        
        self.config: Dict[str, Any] = self._load_config()
        db_cfg = self.config.get("global_settings", {}).get("database", {})
        self.db_path = db_cfg.get("target_path", "d:/VESTA/db/vesta.duckdb")
        self.run_summary: Dict[str, Any] = {
            "started_at": dt.datetime.now().isoformat(),
            "config_path": str(self.config_path),
            "jobs_executed": [],
            "records_ingested": {},
            "errors": [],
        }

    def _load_config(self) -> Dict[str, Any]:
        """Đọc và kiểm tra tính hợp lệ của tệp cấu hình robots_global.yaml."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg or {}

    def get_watermarks(self) -> Dict[str, Any]:
        """Truy vấn các điểm chốt thời gian (watermarks) hiện có trong database để tối ưu cào gia tăng."""
        con = duckdb.connect(self.db_path, read_only=True)
        watermarks = {}
        try:
            # 1. Latest news published timestamp
            row = con.execute("SELECT max(published_at) FROM core.news").fetchone()
            watermarks["latest_news_published_at"] = str(row[0]) if row and row[0] else None

            # 2. Latest macro policy published timestamp
            row = con.execute("SELECT max(published_at) FROM core.macro_policy").fetchone()
            watermarks["latest_macro_policy_published_at"] = str(row[0]) if row and row[0] else None

            # 3. Latest OHLCV daily date
            row = con.execute("SELECT max(date) FROM core.market_ohlcv_daily").fetchone()
            watermarks["latest_ohlcv_date"] = str(row[0]) if row and row[0] else None

            # 4. Total fundamentals rows by source
            rows = con.execute("SELECT source, count(*) FROM core.fundamentals GROUP BY source").fetchall()
            watermarks["fundamentals_breakdown"] = {r[0]: r[1] for r in rows}

            # 5. Latest research reports date
            row = con.execute("SELECT max(report_date) FROM core.stock_research_reports").fetchone()
            watermarks["latest_research_report_date"] = str(row[0]) if row and row[0] else None

        except Exception as e:
            logger.warning(f"Error querying database watermarks: {e}")
        finally:
            con.close()

        return watermarks

    def run_tier1_api(self, modules: Optional[List[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Thực thi Tier 1: Cào dữ liệu xương sống từ API vnstock/vnstock_data."""
        logger.info("=================================================================")
        logger.info(">>> [TIER 1] KHỞI CHẠY API CRAWLER: VNSTOCK / VNSTOCK_DATA <<<")
        logger.info("=================================================================")
        t1_cfg = self.config.get("tier1_vnstock_api", {}).get("modules", {})
        selected = modules or list(t1_cfg.keys())
        results = {}

        for mod_name in selected:
            if mod_name not in t1_cfg:
                logger.warning(f"Bỏ qua module Tier 1 không xác định: {mod_name}")
                continue
            mod_info = t1_cfg[mod_name]
            logger.info(f"-> [Tier 1] Bắt đầu module: {mod_name} ({mod_info.get('description', '')})")

            if dry_run:
                logger.info(f"   [DRY-RUN] Sẽ gọi crawler: {mod_info.get('module_path')} -> {mod_info.get('target_table')}")
                results[mod_name] = {"status": "dry_run", "records": 0}
                continue

            start_t = time.time()
            records = 0
            try:
                top_symbols = ["VCB", "VNM", "HPG", "FPT", "VIC"]
                if mod_name == "dim_symbol":
                    from src.crawlers import dim_symbol
                    res = dim_symbol.run()
                    records = res if isinstance(res, int) else (res.get("written", 0) if isinstance(res, dict) else 0)

                elif mod_name == "market_ohlcv":
                    from src.crawlers import market_ohlcv
                    start_date = (dt.date.today() - dt.timedelta(days=7)).strftime("%Y-%m-%d")
                    for sym in top_symbols:
                        try:
                            n = market_ohlcv.run(sym, start=start_date)
                            records += (n if isinstance(n, int) else 0)
                        except Exception as e_sym:
                            logger.warning(f"Lỗi tải OHLCV {sym}: {e_sym}")

                elif mod_name == "corporate_news":
                    from src.crawlers import vnstock_news
                    for sym in top_symbols:
                        try:
                            n = vnstock_news.run(sym)
                            records += (n if isinstance(n, int) else 0)
                        except Exception as e_sym:
                            logger.warning(f"Lỗi tải tin {sym}: {e_sym}")

                elif mod_name == "fundamentals":
                    from src.crawlers import fundamentals
                    for sym in top_symbols[:3]:
                        try:
                            n = fundamentals.run(sym, report_type="all")
                            records += (n if isinstance(n, int) else 0)
                        except Exception as e_sym:
                            logger.warning(f"Lỗi tải BCTC {sym}: {e_sym}")

                elif mod_name == "corporate_events":
                    from src.crawlers import corporate_events
                    for sym in top_symbols:
                        try:
                            n = corporate_events.run(sym)
                            records += (n if isinstance(n, int) else 0)
                        except Exception as e_sym:
                            logger.warning(f"Lỗi tải sự kiện {sym}: {e_sym}")

                elif mod_name == "quote_snapshots":
                    from src.crawlers import snapshots
                    try:
                        n = snapshots.run(top_symbols)
                        records += (n if isinstance(n, int) else 0)
                    except Exception as e_snap:
                        logger.warning(f"Lỗi tải snapshots: {e_snap}")

                results[mod_name] = {
                    "status": "success",
                    "records": records,
                    "duration_seconds": round(time.time() - start_t, 2),
                }
                logger.info(f"   [OK] {mod_name}: +{records} bản ghi ({round(time.time() - start_t, 2)}s)")

            except Exception as e:
                logger.error(f"   [ERROR] Module {mod_name} thất bại: {e}")
                results[mod_name] = {"status": "failed", "error": str(e)}
                self.run_summary["errors"].append({"tier": 1, "module": mod_name, "error": str(e)})

        return results

    def run_tier2_enhancers(self, targets: Optional[List[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Thực thi Tier 2: Nạp bổ sung dữ liệu khuyết thiếu từ CafeF & Vietstock."""
        logger.info("=================================================================")
        logger.info(">>> [TIER 2] KHỞI CHẠY BỘ ENHANCER: CAFEF & VIETSTOCK FINANCE <<<")
        logger.info("=================================================================")
        t2_cfg = self.config.get("tier2_enhancers", {})
        results = {}

        # 1. CafeF Enhancers
        cafef_cfg = t2_cfg.get("cafef", {})
        cafef_features = cafef_cfg.get("features", {})
        for feat_name, feat_info in cafef_features.items():
            if targets and feat_name not in targets and "cafef" not in targets:
                continue
            logger.info(f"-> [Tier 2 CafeF] Đang chạy tính năng: {feat_name}")
            if dry_run:
                logger.info(f"   [DRY-RUN] Sẽ gọi: {feat_info.get('module_path')} -> {feat_info.get('target_table')}")
                results[f"cafef_{feat_name}"] = {"status": "dry_run", "records": 0}
                continue

            start_t = time.time()
            records = 0
            try:
                if feat_name == "balance_sheet_enhancer":
                    from src.crawlers.cafef_finance_enhancer import CafeFFinanceEnhancer
                    enhancer = CafeFFinanceEnhancer(duckdb_path=self.db_path, delay=0.8)
                    active_symbols = ["VNM", "VCB", "HPG", "FPT", "VIC"]
                    records = enhancer.enhance_symbols(active_symbols, report_types=["cdkt"]) if hasattr(enhancer, "enhance_symbols") else 0

                elif feat_name == "market_indices":
                    from src.crawlers.cafef_data_market import CafeFMarketDataEnhancer
                    enhancer = CafeFMarketDataEnhancer(duckdb_path=self.db_path)
                    records = enhancer.ingest_market_index() if hasattr(enhancer, "ingest_market_index") else 0

                elif feat_name == "foreign_flow_volume":
                    from src.crawlers.cafef_foreign_flow import run_cafef_foreign_flow
                    records = run_cafef_foreign_flow(duckdb_path=self.db_path, days_back=3) if callable(run_cafef_foreign_flow) else 0

                results[f"cafef_{feat_name}"] = {
                    "status": "success",
                    "records": records,
                    "duration_seconds": round(time.time() - start_t, 2),
                }
                logger.info(f"   [OK] cafef_{feat_name}: +{records} bản ghi ({round(time.time() - start_t, 2)}s)")

            except Exception as e:
                logger.error(f"   [ERROR] cafef_{feat_name} lỗi: {e}")
                results[f"cafef_{feat_name}"] = {"status": "failed", "error": str(e)}
                self.run_summary["errors"].append({"tier": 2, "enhancer": f"cafef_{feat_name}", "error": str(e)})

        # 2. Vietstock Enhancers
        vs_cfg = t2_cfg.get("vietstock", {})
        vs_features = vs_cfg.get("features", {})
        for feat_name, feat_info in vs_features.items():
            if targets and feat_name not in targets and "vietstock" not in targets:
                continue
            logger.info(f"-> [Tier 2 Vietstock] Đang chạy tính năng: {feat_name}")
            if dry_run:
                logger.info(f"   [DRY-RUN] Sẽ gọi: {feat_info.get('module_path')} -> {feat_info.get('target_table')}")
                results[f"vietstock_{feat_name}"] = {"status": "dry_run", "records": 0}
                continue

            start_t = time.time()
            records = 0
            try:
                if feat_name == "equity_research_reports":
                    from src.crawlers.vietstock_finance_enhancer import VietstockFinanceEnhancer
                    enhancer = VietstockFinanceEnhancer(duckdb_path=self.db_path, delay=1.2)
                    res = enhancer.crawl(max_pages=2) if hasattr(enhancer, "crawl") else 0
                    records = res if isinstance(res, int) else (res.get("written", 0) if isinstance(res, dict) else 0)

                results[f"vietstock_{feat_name}"] = {
                    "status": "success",
                    "records": records,
                    "duration_seconds": round(time.time() - start_t, 2),
                }
                logger.info(f"   [OK] vietstock_{feat_name}: +{records} bản ghi ({round(time.time() - start_t, 2)}s)")

            except Exception as e:
                logger.error(f"   [ERROR] vietstock_{feat_name} lỗi: {e}")
                results[f"vietstock_{feat_name}"] = {"status": "failed", "error": str(e)}
                self.run_summary["errors"].append({"tier": 2, "enhancer": f"vietstock_{feat_name}", "error": str(e)})

        return results

    def run_tier3_macro_policy(self, categories: Optional[List[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Thực thi Tier 3: Cào tin tức chính sách, luật kinh tế, hiệp hội ngành & vĩ mô quốc tế."""
        logger.info("=================================================================")
        logger.info(">>> [TIER 3] KHỞI CHẠY MACRO, VĂN BẢN PHÁP LUẬT & HIỆP HỘI NGÀNH <<<")
        logger.info("=================================================================")
        t3_cfg = self.config.get("tier3_sources", {})
        results = {}

        # 1. Báo Chính phủ & Văn bản quy phạm pháp luật
        if not categories or "macro_regulatory" in categories or "baochinhphu" in categories:
            logger.info("-> [Tier 3] Quét nghị quyết Chính phủ: Báo Chính phủ (baochinhphu.vn)")
            if dry_run:
                results["baochinhphu"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.baochinhphu_crawler import run_baochinhphu_crawler
                    res = run_baochinhphu_crawler(max_pages=2, db_path=self.db_path)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["baochinhphu"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] baochinhphu: +{records} văn bản/chỉ đạo mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] baochinhphu lỗi: {e}")
                    results["baochinhphu"] = {"status": "failed", "error": str(e)}

        # 2. Báo Đầu tư (baodautu.vn)
        if not categories or "financial_media_portals" in categories or "baodautu" in categories:
            logger.info("-> [Tier 3] Quét báo chí đầu tư & FDI: Báo Đầu tư (baodautu.vn)")
            if dry_run:
                results["baodautu"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.baodautu_crawler import run_baodautu_crawler
                    res = run_baodautu_crawler(max_pages=2, db_path=self.db_path)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["baodautu"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] baodautu: +{records} bài viết đầu tư mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] baodautu lỗi: {e}")
                    results["baodautu"] = {"status": "failed", "error": str(e)}

        # 3. Tin Nhanh Chứng Khoán (tinnhanhchungkhoan.vn)
        if not categories or "financial_media_portals" in categories or "tinnhanhchungkhoan" in categories:
            logger.info("-> [Tier 3] Quét tin tức chứng khoán: Tin Nhanh Chứng Khoán")
            if dry_run:
                results["tinnhanhchungkhoan"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.tinnhanhchungkhoan_crawler import TinNhanhChungKhoanCrawler
                    crawler = TinNhanhChungKhoanCrawler(duckdb_path=self.db_path, delay=0.8)
                    current_month = dt.datetime.now().strftime("%Y-%m")
                    records = crawler.crawl(months=[current_month], max_articles=50)
                    results["tinnhanhchungkhoan"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] tinnhanhchungkhoan: +{records} tin mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] tinnhanhchungkhoan lỗi: {e}")
                    results["tinnhanhchungkhoan"] = {"status": "failed", "error": str(e)}

        # 4. Hiệp hội Thủy sản VASEP (vasep.com.vn)
        if not categories or "industry_associations" in categories or "vasep" in categories:
            logger.info("-> [Tier 3] Quét thông tin ngành thủy sản: VASEP")
            if dry_run:
                results["vasep"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vasep_crawler import VasepCrawler
                    crawler = VasepCrawler(duckdb_path=self.db_path, delay=1.0)
                    records = crawler.crawl(days_back=7, max_articles=25)
                    results["vasep"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] vasep: +{records} tin tức xuất nhập khẩu mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vasep lỗi: {e}")
                    results["vasep"] = {"status": "failed", "error": str(e)}

        # 5. Hiệp hội Ngân hàng VNBA (vnba.org.vn)
        if not categories or "industry_associations" in categories or "vnba" in categories:
            logger.info("-> [Tier 3] Quét chính sách ngân hàng: VNBA (vnba.org.vn)")
            if dry_run:
                results["vnba"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vnba_crawler import run_vnba_crawler
                    res = run_vnba_crawler(db_path=self.db_path, max_articles_per_cat=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vnba"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] vnba: +{records} bài viết chính sách ngân hàng mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vnba lỗi: {e}")
                    results["vnba"] = {"status": "failed", "error": str(e)}

        # 6. Hiệp hội Thép VSA (vsa.com.vn)
        if not categories or "industry_associations" in categories or "vsa" in categories:
            logger.info("-> [Tier 3] Quét số liệu ngành thép & phòng vệ thương mại: VSA (vsa.com.vn)")
            if dry_run:
                results["vsa"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vsa_crawler import run_vsa_crawler
                    res = run_vsa_crawler(db_path=self.db_path, max_articles_per_cat=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vsa"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] vsa: +{records} tin tức/báo cáo thép mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vsa lỗi: {e}")
                    results["vsa"] = {"status": "failed", "error": str(e)}

        # 7. Hiệp hội Logistics VLA (vla.com.vn)
        if not categories or "industry_associations" in categories or "vla" in categories:
            logger.info("-> [Tier 3] Quét cước vận tải biển & logistics: VLA (vla.com.vn)")
            if dry_run:
                results["vla"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vla_crawler import run_vla_crawler
                    res = run_vla_crawler(db_path=self.db_path, max_articles_per_cat=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vla"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] vla: +{records} tin tức logistics mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vla lỗi: {e}")
                    results["vla"] = {"status": "failed", "error": str(e)}

        # 8. Hội Dầu khí Việt Nam (hoidaukhi.vn)
        if not categories or "industry_associations" in categories or "hoidaukhi" in categories:
            logger.info("-> [Tier 3] Quét chính sách năng lượng & dầu khí: Hội Dầu khí (hoidaukhi.vn)")
            if dry_run:
                results["hoidaukhi"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.hoidaukhi_crawler import run_hoidaukhi_crawler
                    res = run_hoidaukhi_crawler(db_path=self.db_path, max_articles_per_cat=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["hoidaukhi"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] hoidaukhi: +{records} tin tức dầu khí mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] hoidaukhi lỗi: {e}")
                    results["hoidaukhi"] = {"status": "failed", "error": str(e)}

        # 9. Thư Viện Pháp Luật (thuvienphapluat.vn)
        if not categories or "economical_laws_policies" in categories or "thuvienphapluat" in categories:
            logger.info("-> [Tier 3] Quét văn bản pháp luật mới: Thư Viện Pháp Luật")
            if dry_run:
                results["thuvienphapluat"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.thuvienphapluat_crawler import run_thuvienphapluat_crawler
                    res = run_thuvienphapluat_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["thuvienphapluat"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] thuvienphapluat: +{records} văn bản mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] thuvienphapluat lỗi: {e}")
                    results["thuvienphapluat"] = {"status": "failed", "error": str(e)}

        # 10. Luật Việt Nam (luatvietnam.vn)
        if not categories or "economical_laws_policies" in categories or "luatvietnam" in categories:
            logger.info("-> [Tier 3] Quét chính sách pháp lý: LuatVietnam")
            if dry_run:
                results["luatvietnam"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.luatvietnam_crawler import run_luatvietnam_crawler
                    res = run_luatvietnam_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["luatvietnam"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] luatvietnam: +{records} bài viết pháp lý mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] luatvietnam lỗi: {e}")
                    results["luatvietnam"] = {"status": "failed", "error": str(e)}

        # 11. Thời báo Tài chính Việt Nam (thoibaotaichinhvietnam.vn)
        if not categories or "financial_media_portals" in categories or "thoibaotaichinh" in categories:
            logger.info("-> [Tier 3] Quét tin tức tài chính & chứng khoán: Thời báo Tài chính")
            if dry_run:
                results["thoibaotaichinh"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.thoibaotaichinh_crawler import run_thoibaotaichinh_crawler
                    res = run_thoibaotaichinh_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["thoibaotaichinh"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] thoibaotaichinh: +{records} tin tài chính mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] thoibaotaichinh lỗi: {e}")
                    results["thoibaotaichinh"] = {"status": "failed", "error": str(e)}

        # 12. VietnamFinance (vietnamfinance.vn)
        if not categories or "financial_media_portals" in categories or "vietnamfinance" in categories:
            logger.info("-> [Tier 3] Quét thị trường & FDI: VietnamFinance")
            if dry_run:
                results["vietnamfinance"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vietnamfinance_crawler import run_vietnamfinance_crawler
                    res = run_vietnamfinance_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vietnamfinance"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vietnamfinance: +{records} bài viết thị trường mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vietnamfinance lỗi: {e}")
                    results["vietnamfinance"] = {"status": "failed", "error": str(e)}

        # 13. Hiệp hội Dệt May VITAS (vitas.org.vn)
        if not categories or "industry_associations" in categories or "vntextile" in categories:
            logger.info("-> [Tier 3] Quét xuất khẩu dệt may: VITAS (vitas.org.vn)")
            if dry_run:
                results["vntextile"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vntextile_crawler import run_vntextile_crawler
                    res = run_vntextile_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vntextile"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vntextile: +{records} tin ngành dệt may mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vntextile lỗi: {e}")
                    results["vntextile"] = {"status": "failed", "error": str(e)}

        # 14. Hiệp hội Doanh nghiệp Dược VNPCA (vnpca.org.vn)
        if not categories or "industry_associations" in categories or "vnpca" in categories:
            logger.info("-> [Tier 3] Quét ngành dược phẩm: VNPCA (vnpca.org.vn)")
            if dry_run:
                results["vnpca"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vnpca_crawler import run_vnpca_crawler
                    res = run_vnpca_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vnpca"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vnpca: +{records} tin ngành dược mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vnpca lỗi: {e}")
                    results["vnpca"] = {"status": "failed", "error": str(e)}

        # 15. Hiệp hội Phân bón VFAEA (vfaea.vn)
        if not categories or "industry_associations" in categories or "vfaea" in categories:
            logger.info("-> [Tier 3] Quét ngành phân bón: VFAEA (vfaea.vn)")
            if dry_run:
                results["vfaea"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vfaea_crawler import run_vfaea_crawler
                    res = run_vfaea_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vfaea"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vfaea: +{records} tin ngành phân bón mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vfaea lỗi: {e}")
                    results["vfaea"] = {"status": "failed", "error": str(e)}

        # 16. Hiệp hội Cao su VRA (vra.com.vn)
        if not categories or "industry_associations" in categories or "vra" in categories:
            logger.info("-> [Tier 3] Quét ngành cao su: VRA (vra.com.vn)")
            if dry_run:
                results["vra"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vra_crawler import run_vra_crawler
                    res = run_vra_crawler(db_path=self.db_path, max_articles=3)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vra"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vra: +{records} tin ngành cao su mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vra lỗi: {e}")
                    results["vra"] = {"status": "failed", "error": str(e)}

        # 17. Người Quan Sát (nguoiquansat.vn)
        if not categories or "financial_media_portals" in categories or "nguoiquansat" in categories:
            logger.info("-> [Tier 3] Quét phân tích thị trường: Người Quan Sát")
            if dry_run:
                results["nguoiquansat"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.nguoiquansat_crawler import run_nguoiquansat_crawler
                    res = run_nguoiquansat_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["nguoiquansat"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] nguoiquansat: +{records} bài phân tích mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] nguoiquansat lỗi: {e}")
                    results["nguoiquansat"] = {"status": "failed", "error": str(e)}

        # 18. Tạp chí Công Thương (tapchicongthuong.vn)
        if not categories or "financial_media_portals" in categories or "tapchicongthuong" in categories or "tcct" in categories:
            logger.info("-> [Tier 3] Quét chính sách thương mại & ngành: Tạp chí Công Thương")
            if dry_run:
                results["tcct"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.tapchicongthuong_crawler import run_tapchicongthuong_crawler
                    res = run_tapchicongthuong_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["tcct"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] tcct: +{records} bài viết ngành thương mại mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] tcct lỗi: {e}")
                    results["tcct"] = {"status": "failed", "error": str(e)}

        # 19. Báo Nhân Dân (nhandan.vn)
        if not categories or "financial_media_portals" in categories or "nhandan" in categories:
            logger.info("-> [Tier 3] Quét chính sách vĩ mô: Báo Nhân Dân")
            if dry_run:
                results["nhandan"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.nhandan_crawler import run_nhandan_crawler
                    res = run_nhandan_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["nhandan"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] nhandan: +{records} bài viết chính sách mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] nhandan lỗi: {e}")
                    results["nhandan"] = {"status": "failed", "error": str(e)}

        # 20. Báo Tiền Phong (tienphong.vn)
        if not categories or "financial_media_portals" in categories or "tienphong" in categories:
            logger.info("-> [Tier 3] Quét kinh tế & doanh nghiệp: Báo Tiền Phong")
            if dry_run:
                results["tienphong"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.tienphong_crawler import run_tienphong_crawler
                    res = run_tienphong_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["tienphong"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] tienphong: +{records} bài viết kinh tế mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] tienphong lỗi: {e}")
                    results["tienphong"] = {"status": "failed", "error": str(e)}

        # 21. World Bank Macro API
        if not categories or "world_macro_institutions" in categories or "worldbank" in categories:
            logger.info("-> [Tier 3] Quét dữ liệu vĩ mô: World Bank Open Data REST API")
            if dry_run:
                results["worldbank"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.worldbank_crawler import WorldBankCrawler
                    crawler = WorldBankCrawler(duckdb_path=self.db_path)
                    records = crawler.crawl()
                    results["worldbank"] = {"status": "success", "records": records}
                    logger.info(f"   [OK] worldbank: +{records} chỉ số vĩ mô nạp thành công.")
                except Exception as e:
                    logger.error(f"   [ERROR] worldbank lỗi: {e}")
                    results["worldbank"] = {"status": "failed", "error": str(e)}

        # 22. Hiệp hội Thương mại Điện tử VECOM (vecom.vn)
        if not categories or "industry_associations" in categories or "vecom" in categories:
            logger.info("-> [Tier 3] Quét thương mại điện tử: VECOM (vecom.vn)")
            if dry_run:
                results["vecom"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vecom_crawler import run_vecom_crawler
                    res = run_vecom_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vecom"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vecom: +{records} bài viết TMĐT mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vecom lỗi: {e}")
                    results["vecom"] = {"status": "failed", "error": str(e)}

        # 23. Hiệp hội các Nhà sản xuất Ô tô VAMA (vama.org.vn)
        if not categories or "industry_associations" in categories or "vama" in categories:
            logger.info("-> [Tier 3] Quét thị trường ô tô: VAMA (vama.org.vn)")
            if dry_run:
                results["vama"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vama_crawler import run_vama_crawler
                    res = run_vama_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vama"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vama: +{records} bài viết ô tô mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vama lỗi: {e}")
                    results["vama"] = {"status": "failed", "error": str(e)}

        # 24. Hiệp hội Doanh nghiệp Đầu tư Nước ngoài VAFIE (vafie.org.vn)
        if not categories or "industry_associations" in categories or "vafie" in categories:
            logger.info("-> [Tier 3] Quét dòng vốn FDI & chính sách đầu tư: VAFIE (vafie.org.vn)")
            if dry_run:
                results["vafie"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vafie_crawler import run_vafie_crawler
                    res = run_vafie_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vafie"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vafie: +{records} bài viết FDI mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vafie lỗi: {e}")
                    results["vafie"] = {"status": "failed", "error": str(e)}

        # 25. Hiệp hội Doanh nghiệp Điện tử Việt Nam VEIA (veia.org.vn)
        if not categories or "industry_associations" in categories or "viea" in categories:
            logger.info("-> [Tier 3] Quét công nghệ & bán dẫn: VEIA (veia.org.vn)")
            if dry_run:
                results["viea"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.viea_crawler import run_viea_crawler
                    res = run_viea_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["viea"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] viea: +{records} bài viết điện tử mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] viea lỗi: {e}")
                    results["viea"] = {"status": "failed", "error": str(e)}

        # 26. Hiệp hội Doanh nghiệp TP.HCM HUBA (huba.vn)
        if not categories or "industry_associations" in categories or "huba" in categories:
            logger.info("-> [Tier 3] Quét diễn đàn & doanh nghiệp TP.HCM: HUBA (huba.vn)")
            if dry_run:
                results["huba"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.huba_crawler import run_huba_crawler
                    res = run_huba_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["huba"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] huba: +{records} bài viết doanh nghiệp TP.HCM mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] huba lỗi: {e}")
                    results["huba"] = {"status": "failed", "error": str(e)}

        # 27. Báo Tuổi Trẻ (tuoitre.vn)
        if not categories or "financial_media_portals" in categories or "tuoitre" in categories:
            logger.info("-> [Tier 3] Quét kinh doanh & kinh tế: Báo Tuổi Trẻ (tuoitre.vn)")
            if dry_run:
                results["tuoitre"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.tuoitre_crawler import run_tuoitre_crawler
                    res = run_tuoitre_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["tuoitre"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] tuoitre: +{records} bài viết kinh doanh mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] tuoitre lỗi: {e}")
                    results["tuoitre"] = {"status": "failed", "error": str(e)}

        # 28. Hiệp hội Hồ tiêu và Cây gia vị VPSA (vpsaspice.org)
        if not categories or "industry_associations" in categories or "vpsaspice" in categories:
            logger.info("-> [Tier 3] Quét nông sản & hồ tiêu: VPSA (vpsaspice.org)")
            if dry_run:
                results["vpsaspice"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vpsaspice_crawler import run_vpsaspice_crawler
                    res = run_vpsaspice_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vpsaspice"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vpsaspice: +{records} bài viết hồ tiêu mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vpsaspice lỗi: {e}")
                    results["vpsaspice"] = {"status": "failed", "error": str(e)}

        # 29. Hiệp hội Bệnh viện tư nhân HHBVT (hiephoibenhvientu.com.vn)
        if not categories or "industry_associations" in categories or "hhbvt" in categories:
            logger.info("-> [Tier 3] Quét y tế & bệnh viện tư: HHBVT (hiephoibenhvientu.com.vn)")
            if dry_run:
                results["hhbvt"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.hhbvt_crawler import run_hhbvt_crawler
                    res = run_hhbvt_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["hhbvt"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] hhbvt: +{records} bài viết y tế mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] hhbvt lỗi: {e}")
                    results["hhbvt"] = {"status": "failed", "error": str(e)}

        # 30. Hội Năng lượng Nguyên tử / Sạch AVNUC (avnuc.vn)
        if not categories or "industry_associations" in categories or "avnuc" in categories:
            logger.info("-> [Tier 3] Quét năng lượng sạch: AVNUC (avnuc.vn)")
            if dry_run:
                results["avnuc"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.avnuc_crawler import run_avnuc_crawler
                    res = run_avnuc_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["avnuc"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] avnuc: +{records} bài viết năng lượng mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] avnuc lỗi: {e}")
                    results["avnuc"] = {"status": "failed", "error": str(e)}

        # 31. Hiệp hội Doanh nghiệp Nhỏ và Vừa VINASME (vinasme.vn)
        if not categories or "industry_associations" in categories or "vinasme" in categories:
            logger.info("-> [Tier 3] Quét khối SME: VINASME (vinasme.vn)")
            if dry_run:
                results["vinasme"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vinasme_crawler import run_vinasme_crawler
                    res = run_vinasme_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vinasme"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vinasme: +{records} bài viết SME mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vinasme lỗi: {e}")
                    results["vinasme"] = {"status": "failed", "error": str(e)}

        # 32. Hiệp hội Phát triển Hàng tiêu dùng VACOD (vacod.vn)
        if not categories or "industry_associations" in categories or "vacod" in categories:
            logger.info("-> [Tier 3] Quét hàng tiêu dùng: VACOD (vacod.vn)")
            if dry_run:
                results["vacod"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vacod_crawler import run_vacod_crawler
                    res = run_vacod_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vacod"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vacod: +{records} bài viết hàng tiêu dùng mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vacod lỗi: {e}")
                    results["vacod"] = {"status": "failed", "error": str(e)}

        # 33. Liên hiệp các Hội Khoa học & Kỹ thuật VUSTA (vusta.vn)
        if not categories or "industry_associations" in categories or "vusta" in categories:
            logger.info("-> [Tier 3] Quét KH&CN: VUSTA (vusta.vn)")
            if dry_run:
                results["vusta"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.vusta_crawler import run_vusta_crawler
                    res = run_vusta_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["vusta"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] vusta: +{records} bài viết KH&CN mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] vusta lỗi: {e}")
                    results["vusta"] = {"status": "failed", "error": str(e)}

        # 34. Hiệp hội Internet Việt Nam VIA (via.org.vn)
        if not categories or "industry_associations" in categories or "via" in categories:
            logger.info("-> [Tier 3] Quét Internet & số hóa: VIA (via.org.vn)")
            if dry_run:
                results["via"] = {"status": "dry_run", "records": 0}
            else:
                try:
                    from src.crawlers.via_crawler import run_via_crawler
                    res = run_via_crawler(db_path=self.db_path, max_articles=5)
                    records = res.get("total_written", 0) if isinstance(res, dict) else 0
                    results["via"] = {"status": res.get("status", "success"), "records": records}
                    logger.info(f"   [OK] via: +{records} bài viết Internet mới.")
                except Exception as e:
                    logger.error(f"   [ERROR] via lỗi: {e}")
                    results["via"] = {"status": "failed", "error": str(e)}

        return results

    def run_daily_pipeline(self, tier: str = "all", dry_run: bool = False) -> Dict[str, Any]:
        """Chạy tổng hợp toàn bộ các tầng dữ liệu theo lịch trình hàng ngày."""
        start_time = time.time()
        logger.info(f"*** BẮT ĐẦU VESTA DAILY CRAWLER PIPELINE (TIER: {tier.upper()}, DRY-RUN: {dry_run}) ***")

        # 1. Print current watermarks
        watermarks = self.get_watermarks()
        logger.info(f"==> Database Watermarks hiện tại:")
        for k, v in watermarks.items():
            logger.info(f"    - {k}: {v}")

        summary = {"tier1": {}, "tier2": {}, "tier3": {}, "total_records": 0}

        if tier in ("1", "all"):
            summary["tier1"] = self.run_tier1_api(dry_run=dry_run)

        if tier in ("2", "all"):
            summary["tier2"] = self.run_tier2_enhancers(dry_run=dry_run)

        if tier in ("3", "all"):
            summary["tier3"] = self.run_tier3_macro_policy(dry_run=dry_run)

        # Calculate total records
        total = 0
        for t_key in ("tier1", "tier2", "tier3"):
            for item in summary[t_key].values():
                total += item.get("records", 0)
        summary["total_records"] = total
        summary["duration_seconds"] = round(time.time() - start_time, 2)
        summary["finished_at"] = dt.datetime.now().isoformat()

        # Save summary report
        out_dir = PROJECT_ROOT / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        date_str = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        report_file = out_dir / f"daily_crawl_run_{date_str}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        logger.info("=================================================================")
        logger.info(f"*** HOÀN TẤT DAILY CRAWL: +{total} BẢN GHI MỚI TRONG {summary['duration_seconds']}s ***")
        logger.info(f"*** Báo cáo lưu tại: {report_file} ***")
        logger.info("=================================================================")
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA Daily Multi-Tier Crawler Orchestrator")
    parser.add_argument(
        "--config",
        default="configs/robots_global.yaml",
        help="Đường dẫn file cấu hình robots toàn cục",
    )
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Chọn tầng cần cào: 1 (API vnstock), 2 (Enhancer CafeF/Vietstock), 3 (Macro & Media), all (Tất cả)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ kiểm tra watermark và cấu hình mà không ghi vào DuckDB",
    )
    args = parser.parse_args()

    orchestrator = DailyCrawlerOrchestrator(config_path=args.config)
    orchestrator.run_daily_pipeline(tier=args.tier, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
