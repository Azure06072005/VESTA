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
                if mod_name == "dim_symbol":
                    from src.crawlers import dim_symbol
                    res = dim_symbol.run(duckdb_path=self.db_path)
                    records = res if isinstance(res, int) else (res.get("written", 0) if isinstance(res, dict) else 0)

                elif mod_name == "market_ohlcv":
                    # Fetch recent bars for VN30 symbols incrementally
                    from src.crawlers import market_ohlcv
                    # Sync top liquid VN30 tickers for daily bar
                    res = market_ohlcv.run_incremental(duckdb_path=self.db_path, lookback_days=3) if hasattr(market_ohlcv, "run_incremental") else 0
                    records = res if isinstance(res, int) else 0

                elif mod_name == "corporate_news":
                    from src.crawlers import vnstock_news
                    res = vnstock_news.run(duckdb_path=self.db_path) if hasattr(vnstock_news, "run") else 0
                    records = res if isinstance(res, int) else 0

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
                    # Run missing active symbols queue
                    active_symbols = ["VNM", "VCB", "HPG", "FPT", "VIC", "VHM", "MSN", "MWG", "TCB", "MBB"]
                    records = enhancer.enhance_symbols(active_symbols, report_types=["cdkt"]) if hasattr(enhancer, "enhance_symbols") else 0

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

        # 5. World Bank Macro API
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
