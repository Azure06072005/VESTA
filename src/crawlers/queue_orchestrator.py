"""Multi-Source Crawling Queue Orchestrator.

Bộ điều phối hàng đợi thu thập dữ liệu đa nguồn (Multi-Source Crawling Queue):
- Tin Nhanh Chứng Khoán (`tinnhanhchungkhoan.vn`)
- Hiệp hội Thủy sản VASEP (`vasep.com.vn`)
- Ngân hàng Thế giới World Bank Macro Data (`data.worldbank.org`)
- Tự động chạy tuần tự, chống xung đột khóa DuckDB và kiểm soát tốc độ request.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawlers.tinnhanhchungkhoan_crawler import TinNhanhChungKhoanCrawler
from crawlers.vasep_crawler import VasepCrawler
from crawlers.worldbank_crawler import WorldBankCrawler

logger = logging.getLogger(__name__)


class CrawlJob:
    """Định nghĩa một công việc trong hàng đợi cào dữ liệu."""

    def __init__(self, name: str, description: str, runner: Callable[[], int]):
        self.name = name
        self.description = description
        self.runner = runner
        self.status = "pending"
        self.items_ingested = 0
        self.error: str | None = None
        self.duration_seconds = 0.0


class MultiSourceQueueOrchestrator:
    """Bộ quản lý hàng đợi và điều phối thực thi các nguồn cào dữ liệu."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb", delay_between_jobs: float = 2.0):
        self.duckdb_path = duckdb_path
        self.delay_between_jobs = delay_between_jobs
        self.jobs: list[CrawlJob] = []
        self._init_queue()

    def _init_queue(self) -> None:
        """Khởi tạo danh sách các nguồn cào trong hàng đợi."""
        tnck_crawler = TinNhanhChungKhoanCrawler(duckdb_path=self.duckdb_path, delay=0.8)
        vasep_crawler = VasepCrawler(duckdb_path=self.duckdb_path, delay=1.0)
        wb_crawler = WorldBankCrawler(duckdb_path=self.duckdb_path)

        self.jobs = [
            CrawlJob(
                name="worldbank",
                description="Chỉ số kinh tế vĩ mô Việt Nam từ World Bank REST API",
                runner=lambda: wb_crawler.crawl(),
            ),
            CrawlJob(
                name="tinnhanhchungkhoan",
                description="Tin tức chuyên sâu thị trường & doanh nghiệp Tin Nhanh Chứng Khoán",
                runner=lambda: tnck_crawler.crawl(months=["2026-9", "2026-8"], max_articles=200),
            ),
            CrawlJob(
                name="vasep",
                description="Báo cáo xuất nhập khẩu & quy định thị trường thủy sản VASEP",
                runner=lambda: vasep_crawler.crawl(days_back=15, max_articles=100),
            ),
        ]

    def run_job(self, job_name: str) -> CrawlJob | None:
        """Chạy đơn lẻ một job theo tên."""
        for job in self.jobs:
            if job.name == job_name:
                self._execute(job)
                return job
        return None

    def run_all(self) -> list[CrawlJob]:
        """Chạy toàn bộ hàng đợi lần lượt."""
        logger.info(f"==> Bắt đầu thực thi hàng đợi gồm {len(self.jobs)} nguồn dữ liệu...")
        for i, job in enumerate(self.jobs, 1):
            logger.info(f"\n--- [Hàng đợi {i}/{len(self.jobs)}] Khởi chạy nguồn: {job.name.upper()} ---")
            self._execute(job)
            time.sleep(self.delay_between_jobs)
        logger.info("\n==> Hoàn tất toàn bộ hàng đợi cào dữ liệu!")
        return self.jobs

    def _execute(self, job: CrawlJob) -> None:
        """Thực thi một job với đo lường thời gian và xử lý ngoại lệ an toàn."""
        start_t = time.time()
        job.status = "running"
        try:
            cnt = job.runner()
            job.items_ingested = cnt
            job.status = "success"
            logger.info(f"  -> [Thành công] {job.name}: Đã nạp +{cnt} bản ghi.")
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            logger.error(f"  -> [Thất bại] {job.name}: {e}")
        finally:
            job.duration_seconds = time.time() - start_t


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Multi-Source Crawling Queue Orchestrator")
    parser.add_argument("--job", choices=["all", "worldbank", "tinnhanhchungkhoan", "vasep"], default="all")
    parser.add_argument("--delay", type=float, default=2.0)

    args = parser.parse_args()
    orchestrator = MultiSourceQueueOrchestrator(delay_between_jobs=args.delay)

    if args.job == "all":
        results = orchestrator.run_all()
    else:
        job = orchestrator.run_job(args.job)
        results = [job] if job else []

    print("\n" + "=" * 60)
    print("BÁO CÁO KẾT QUẢ HÀNG ĐỢI THU THẬP DỮ LIỆU:")
    print("=" * 60)
    for r in results:
        print(f"• [{r.status.upper():<7}] Nguồn: {r.name:<20} | Bản ghi: {r.items_ingested:<5} | Thời gian: {r.duration_seconds:.1f}s")


if __name__ == "__main__":
    main()
