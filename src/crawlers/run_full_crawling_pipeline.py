"""src/crawlers/run_full_crawling_pipeline.py

VESTA Full Crawling Pipeline Orchestrator.
Kịch bản hợp nhất điều phối chạy toàn bộ quá trình thu thập dữ liệu Lakehouse:
1. Master Fundamentals Crawler: Báo cáo tài chính, thuyết minh BCTC, sự kiện, dòng tiền tự doanh, khối ngoại, lãi suất vĩ mô, nến OHLCV.
2. Master News Crawler: Tin tức doanh nghiệp, cổng thông tin tài chính, chính sách vĩ mô, hiệp hội ngành nghề, tài chính quốc tế.
3. Lakehouse Buffer Sync: Tự động giải phóng dữ liệu đệm vào vesta_snapshot.duckdb.
4. Terminal Audit Dashboard: Tự động chạy track_crawling_progress để kiểm toán độ phủ sau khi cào xong.

Sử dụng:
    # 1. Cào toàn bộ (VN30, cả 2 luồng, ưu tiên mới nhất -> lịch sử 2000):
    python -m src.crawlers.run_full_crawling_pipeline --scope vn30 --priority both

    # 2. Cào toàn thị trường (All ~1,750 mã):
    python -m src.crawlers.run_full_crawling_pipeline --scope all --priority both

    # 3. Chạy thử nghiệm nhanh (Smoke test 2 mã):
    python -m src.crawlers.run_full_crawling_pipeline --smoke-test
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import pathlib
import sys
import time
from typing import Dict, List, Optional

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crawlers.db_writer import ResilientDuckDBWriter, DEFAULT_TARGET_DB
from crawlers.boundary_manager import BoundaryManager
from crawlers.track_crawling_progress import run_progress_tracker, VN30_SYMBOLS
import duckdb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_full_crawling_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VESTA Master Unified Crawling Pipeline (Fundamentals + News + Policy + Sync)"
    )
    parser.add_argument("--db", default=DEFAULT_TARGET_DB, help="Đường dẫn file DuckDB chính")
    parser.add_argument(
        "--scope",
        default="vn30",
        help="Phạm vi mã cổ phiếu: 'vn30' (30 mã rổ chỉ số), 'all' (toàn bộ ~1,750 mã), hoặc danh sách tùy biến 'VCB,FPT,SSI'",
    )
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "fundamentals", "news"],
        help="Chế độ cào: 'all' (cả số liệu & tin tức), 'fundamentals' (chỉ số liệu BCTC/giá), 'news' (chỉ tin tức & chính sách)",
    )
    parser.add_argument(
        "--priority",
        default="both",
        choices=["forward", "backward", "both"],
        help="Thứ tự ưu tiên dải ngày: 'both' (ưu tiên forward đến hôm nay trước, sau đó backward về 2000), 'forward', 'backward'",
    )
    parser.add_argument(
        "--target-earliest-year",
        type=int,
        default=2000,
        help="Mốc năm sớm nhất cần cào lùi về trong chế độ backward (mặc định: 2000)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bắt buộc cào lại toàn bộ, không bỏ qua các mã hoặc dải ngày đã tồn tại trong database",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Chế độ kiểm tra nhanh đường truyền & parser (chỉ cào 2 mã và giới hạn 5 trang/nguồn)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Thời gian nghỉ giữa các lượt gọi API / web requests (giây)",
    )
    parser.add_argument(
        "--skip-track",
        action="store_true",
        help="Không hiển thị bảng báo cáo kiểm toán tiến trình ở cuối",
    )
    return parser.parse_args()


def resolve_symbols(scope: str, db_path: str) -> List[str]:
    """Phân giải chuỗi phạm vi thành danh sách mã cổ phiếu."""
    scope_clean = scope.strip().lower()
    if scope_clean == "vn30":
        logger.info(">>> Đã chọn phạm vi: Rổ VN30 (%d mã bluechips) <<<", len(VN30_SYMBOLS))
        return VN30_SYMBOLS.copy()

    if scope_clean == "all":
        try:
            con = duckdb.connect(db_path, read_only=True)
            df_sym = con.execute(
                "SELECT symbol FROM core.dim_symbol WHERE is_delisted IS NOT TRUE ORDER BY symbol"
            ).fetchdf()
            con.close()
            symbols = df_sym["symbol"].tolist()
            logger.info(">>> Đã chọn phạm vi: Toàn bộ thị trường (%d mã niêm yết) <<<", len(symbols))
            return symbols
        except Exception as e:
            logger.warning("Không truy vấn được core.dim_symbol (%s), sử dụng fallback VN30.", e)
            return VN30_SYMBOLS.copy()

    custom_symbols = [s.strip().upper() for s in scope.split(",") if s.strip()]
    logger.info(">>> Đã chọn phạm vi tùy biến: %d mã (%s) <<<", len(custom_symbols), custom_symbols[:5])
    return custom_symbols


def execute_pipeline(args: argparse.Namespace) -> int:
    symbols = resolve_symbols(args.scope, args.db)
    if args.smoke_test:
        symbols = symbols[:2]
        logger.info(">>> ĐANG BẬT CHẾ ĐỘ SMOKE TEST (2 mã: %s) <<<", symbols)

    symbols_str = ",".join(symbols)
    writer = ResilientDuckDBWriter(target_db=args.db)

    print("\n" + "=" * 90)
    print("      VESTA ENTERPRISE FULL CRAWLING PIPELINE ORCHESTRATOR")
    print(f"      Thời điểm khởi chạy: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"      Mục tiêu DuckDB   : {args.db}")
    print(f"      Phạm vi mã        : {len(symbols)} mã (Scope={args.scope})")
    print(f"      Chế độ thực thi   : {args.mode.upper()}")
    print(f"      Chiến lược ngày   : {args.priority.upper()} (Năm sớm nhất: {args.target_earliest_year})")
    print(f"      Bỏ qua mã có sẵn  : {'KHÔNG (Force mode)' if args.force else 'CÓ (Skip enabled)'}")
    print("=" * 90 + "\n")

    overall_start = time.time()
    total_records = 0
    phase_stats: Dict[str, int] = {}

    # -------------------------------------------------------------------------
    # PHASE 1: CÀO SỐ LIỆU CƠ BẢN & ĐỊNH LƯỢNG (FUNDAMENTALS & NUMERIC)
    # -------------------------------------------------------------------------
    if args.mode in ("all", "fundamentals"):
        logger.info("\n>>> [GIAI ĐOẠN 1/3]: KHỞI CHẠY MASTER FUNDAMENTALS CRAWLER <<<")
        try:
            from crawlers.master_fundamentals_crawler import main as run_fundamentals_main

            # Thiết lập tham số CLI giả lập cho fundamentals
            sys_argv_backup = sys.argv.copy()
            f_argv = [
                "master_fundamentals_crawler",
                "--db", args.db,
                "--symbols", symbols_str,
                "--sources", "all",
                "--delay", str(args.delay),
            ]
            if args.force:
                f_argv.append("--force")
            if args.smoke_test:
                f_argv.append("--smoke-test")

            sys.argv = f_argv
            f_code = run_fundamentals_main()
            sys.argv = sys_argv_backup

            logger.info(">>> [GIAI ĐOẠN 1/3]: Hoàn tất Master Fundamentals Crawler (code=%d).", f_code)
        except Exception as e:
            logger.error("Lỗi nghiêm trọng tại Giai đoạn 1 (Fundamentals): %s", e, exc_info=True)

    # -------------------------------------------------------------------------
    # PHASE 2: CÀO TIN TỨC & CHÍNH SÁCH VĨ MÔ (NEWS & POLICY RESOURCES)
    # -------------------------------------------------------------------------
    if args.mode in ("all", "news"):
        logger.info("\n>>> [GIAI ĐOẠN 2/3]: KHỞI CHẠY MASTER NEWS CRAWLER <<<")
        try:
            from crawlers.master_news_crawler import main as run_news_main

            sys_argv_backup = sys.argv.copy()
            n_argv = [
                "master_news_crawler",
                "--db", args.db,
                "--symbols", symbols_str,
                "--categories", "all",
                "--sources", "all",
                "--priority", args.priority,
                "--target-earliest-year", str(args.target_earliest_year),
                "--delay", str(args.delay),
            ]
            if args.force:
                n_argv.append("--force")
            if args.smoke_test:
                n_argv.append("--smoke-test")

            sys.argv = n_argv
            n_code = run_news_main()
            sys.argv = sys_argv_backup

            logger.info(">>> [GIAI ĐOẠN 2/3]: Hoàn tất Master News Crawler (code=%d).", n_code)
        except Exception as e:
            logger.error("Lỗi nghiêm trọng tại Giai đoạn 2 (News): %s", e, exc_info=True)

    # -------------------------------------------------------------------------
    # PHASE 3: ĐỒNG BỘ DỮ LIỆU ĐỆM VÀO DATABASE ĐÍCH
    # -------------------------------------------------------------------------
    logger.info("\n>>> [GIAI ĐOẠN 3/3]: ĐỒNG BỘ BUFFER VÀO TARGET DUCKDB <<<")
    synced_tables = writer.sync_buffer_to_target()
    logger.info("Đã đồng bộ %d bảng từ bộ đệm vào %s.", synced_tables, args.db)

    total_duration = time.time() - overall_start
    print("\n" + "=" * 90)
    print(f"      HOÀN TẤT TOÀN BỘ QUÁ TRÌNH THU THẬP TRONG {total_duration:.2f} GIÂY ({total_duration/60:.1f} PHÚT)")
    print("=" * 90 + "\n")

    # -------------------------------------------------------------------------
    # AUDIT TRACKER REPORT
    # -------------------------------------------------------------------------
    if not args.skip_track:
        logger.info("Đang khởi tạo báo cáo Dashboard kiểm toán Lakehouse...")
        try:
            stats = run_progress_tracker(duckdb_path=args.db)
            print("\n[OK] Toàn bộ dữ liệu đã được lưu trữ và kiểm toán an toàn.")
        except Exception as e:
            logger.warning("Lỗi tạo báo cáo kiểm toán: %s", e)

    return 0


def main() -> int:
    args = parse_args()
    return execute_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
