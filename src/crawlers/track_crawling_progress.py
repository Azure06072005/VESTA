"""src/crawlers/track_crawling_progress.py

VESTA Real-Time Crawling & Lakehouse Progress Tracker.
Theo dõi toàn diện tiến độ cào dữ liệu và tình trạng kho dữ liệu DuckDB:
1. Tổng quan tình trạng CSDL: Đường dẫn, kích thước file, kiểm tra khóa file.
2. Bảng thống kê toàn bộ các bảng core:
   - core.news (tin tức theo mã cổ phiếu)
   - core.news_resources (tin tức vĩ mô, báo chí, văn bản chỉ đạo, hiệp hội)
   - core.fundamentals (báo cáo tài chính)
   - core.corporate_events (sự kiện quyền & cổ tức)
   - core.proprietary_flow (giao dịch tự doanh)
   - core.financial_notes (thuyết minh BCTC)
   - core.macro_rates (lãi suất điều hành & TPCP)
   - core.market_ohlcv_daily (nến giá thị trường)
   - core.market_foreign_flow_daily (dòng tiền khối ngoại)
   - core.stock_research_reports (báo cáo phân tích Vietstock)
   - core.cafef_disclosures (văn bản công bố thông tin)
3. Đánh giá khoảng trống ngày (Date Boundary Audit):
   - Đánh giá biên tiến (Forward: max_date -> hôm nay)
   - Đánh giá biên lùi (Backward: min_date -> năm 2000)
4. Độ phủ theo mã cổ phiếu (VN30 & Ngành Chứng khoán).
5. Hàng đợi công việc (meta.crawl_progress) & Danh sách job lỗi cần chạy lại.

HỖ TRỢ CLI:
    python -m src.crawlers.track_crawling_progress
    python -m src.crawlers.track_crawling_progress --watch 5   (tự động cập nhật mỗi 5 giây)
    python -m src.crawlers.track_crawling_progress --json      (xuất báo cáo JSON)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("track_crawling_progress")

DEFAULT_DB_PATH = str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb")
VN30_SYMBOLS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]

CORE_TABLES_CONFIG = [
    ("news", "published_at", "symbol", "Tin tức doanh nghiệp niêm yết"),
    ("news_resources", "published_at", "source", "Tin tức vĩ mô, báo chí & văn bản quy phạm"),
    ("fundamentals", "period_end", "symbol", "Báo cáo tài chính doanh nghiệp"),
    ("corporate_events", "event_date", "symbol", "Sự kiện quyền & cổ tức"),
    ("proprietary_flow", "date", "symbol", "Dòng tiền tự doanh CTCK"),
    ("financial_notes", "fetched_at", "symbol", "Thuyết minh BCTC chuyên sâu"),
    ("macro_rates", "date", "term", "Lãi suất liên ngân hàng & Lợi suất TPCP"),
    ("macro_economic_series", "period_date", "indicator", "Chuỗi 9 chỉ số kinh tế vĩ mô dài hạn"),
    ("company_overview", "as_of_date", "symbol", "Hồ sơ & quản trị chuyên sâu VN30"),
    ("company_shareholders", "update_date", "symbol", "Cơ cấu cổ đông lớn VN30"),
    ("market_ohlcv_daily", "date", "symbol", "Giá nến ngày OHLCV"),
    ("market_foreign_flow_daily", "date", "symbol", "Khối ngoại mua/bán & room ngoại"),
    ("stock_research_reports", "report_date", "symbol", "Báo cáo phân tích CTCK Vietstock"),
    ("cafef_disclosures", "published_at", "symbol", "Công bố thông tin & BCTC PDF"),
]


class CrawlingProgressTracker:
    """Bộ theo dõi và trực quan hóa tiến độ thu thập dữ liệu."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = os.path.abspath(db_path)

    def _connect(self) -> tuple[Optional[duckdb.DuckDBPyConnection], Optional[str]]:
        """Mở kết nối DuckDB ở chế độ đọc an toàn, bắt lỗi khóa file nếu có."""
        try:
            con = duckdb.connect(self.db_path, read_only=True)
            return con, None
        except Exception as e:
            # Thử file dự phòng fresh nếu bị lock
            buf = os.path.abspath(str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb"))
            if os.path.exists(buf):
                try:
                    con = duckdb.connect(buf, read_only=True)
                    return con, f"[FALLBACK TO BUFFER] {os.path.basename(self.db_path)} bị khóa ({e})"
                except Exception:
                    pass
            return None, str(e)

    def generate_report(self) -> Dict[str, Any]:
        """Tạo toàn bộ dữ liệu báo cáo thống kê."""
        now = dt.datetime.now()
        report: Dict[str, Any] = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "db_path": self.db_path,
            "db_size_mb": 0.0,
            "connection_status": "OK",
            "tables": [],
            "news_sources": [],
            "vn30_coverage": {},
            "jobs_summary": {},
        }

        if os.path.exists(self.db_path):
            report["db_size_mb"] = round(os.path.getsize(self.db_path) / (1024 * 1024), 2)

        con, err = self._connect()
        if not con:
            report["connection_status"] = f"LỖI KẾT NỐI: {err}"
            return report

        if err:
            report["connection_status"] = err

        try:
            # 1. Thống kê từng bảng core
            for tbl, date_col, key_col, desc in CORE_TABLES_CONFIG:
                try:
                    actual_tbl = tbl
                    if tbl == "news_resources":
                        has_res = con.execute("""
                            SELECT count(*) FROM duckdb_tables() 
                            WHERE schema_name='core' AND table_name='news_resources'
                        """).fetchone()[0] > 0
                        if not has_res:
                            actual_tbl = "macro_policy"

                    q = f"""
                        SELECT 
                            COUNT(*) as cnt,
                            COUNT(DISTINCT {key_col}) as unique_keys,
                            MIN({date_col}) as min_d,
                            MAX({date_col}) as max_d
                        FROM core.{actual_tbl}
                    """
                    row = con.execute(q).fetchone()
                    cnt, u_keys, min_d, max_d = row if row else (0, 0, None, None)
                    min_str = str(min_d)[:10] if min_d else "—"
                    max_str = str(max_d)[:10] if max_d else "—"

                    # Đánh giá độ tươi
                    today_str = now.strftime("%Y-%m-%d")
                    if max_str != "—" and max_str >= "2026-09-10":
                        status = "ĐÃ CẬP NHẬT (MỚI NHẤT)"
                    elif max_str != "—":
                        status = f"CẦN CÀO TIẾN ({max_str} -> {today_str})"
                    else:
                        status = "CHƯA CÓ DỮ LIỆU"

                    report["tables"].append({
                        "table": f"core.{tbl}",
                        "description": desc,
                        "records": cnt,
                        "unique_keys": u_keys,
                        "min_date": min_str,
                        "max_date": max_str,
                        "freshness": status,
                    })
                except Exception as ex:
                    report["tables"].append({
                        "table": f"core.{tbl}",
                        "description": desc,
                        "records": 0,
                        "unique_keys": 0,
                        "min_date": "Lỗi",
                        "max_date": "Lỗi",
                        "freshness": f"Bỏ qua: {ex}",
                    })

            # 2. Chi tiết từng nguồn trong core.news và core.news_resources / core.macro_policy
            try:
                # Kiểm tra bảng news_resources hay macro_policy có sẵn trong database
                has_news_res = con.execute("""
                    SELECT count(*) FROM duckdb_tables() 
                    WHERE schema_name = 'core' AND table_name = 'news_resources'
                """).fetchone()[0] > 0
                policy_tbl = "core.news_resources" if has_news_res else "core.macro_policy"

                q_news = f"""
                    SELECT 
                        'core.news' as category,
                        source,
                        COUNT(*) as total,
                        STRFTIME(MIN(published_at), '%Y-%m-%d') as min_d,
                        STRFTIME(MAX(published_at), '%Y-%m-%d') as max_d
                    FROM core.news
                    GROUP BY source
                    UNION ALL
                    SELECT 
                        'core.news_resources' as category,
                        source,
                        COUNT(*) as total,
                        STRFTIME(MIN(published_at), '%Y-%m-%d') as min_d,
                        STRFTIME(MAX(published_at), '%Y-%m-%d') as max_d
                    FROM {policy_tbl}
                    GROUP BY source
                    ORDER BY total DESC
                """
                rows = con.execute(q_news).fetchall()
                today_s = now.strftime("%Y-%m-%d")
                for cat, src, tot, min_d, max_d in rows:
                    fwd_gap = "Đạt" if (max_d and max_d >= "2026-09-10") else f"{max_d} -> {today_s}"
                    bwd_gap = "Đạt" if (min_d and min_d <= "2000-12-31") else f"2000 -> {min_d}"
                    report["news_sources"].append({
                        "category": cat,
                        "source": src,
                        "total_articles": tot,
                        "min_date": min_d or "—",
                        "max_date": max_d or "—",
                        "forward_gap": fwd_gap,
                        "backward_gap": bwd_gap,
                    })
            except Exception as ex:
                logger.debug("Lỗi thống kê news sources: %s", ex)

            # 3. Độ phủ VN30
            try:
                values_str = ", ".join([f"('{s}')" for s in VN30_SYMBOLS])
                q_vn30 = f"""
                    SELECT 
                        s.symbol,
                        (SELECT COUNT(*) FROM core.market_ohlcv_daily o WHERE o.symbol = s.symbol) as ohlcv_cnt,
                        (SELECT COUNT(*) FROM core.fundamentals f WHERE f.symbol = s.symbol) as fun_cnt,
                        (SELECT COUNT(*) FROM core.news n WHERE n.symbol = s.symbol) as news_cnt,
                        (SELECT COUNT(*) FROM core.corporate_events e WHERE e.symbol = s.symbol) as ev_cnt,
                        (SELECT COUNT(*) FROM core.proprietary_flow p WHERE p.symbol = s.symbol) as flow_cnt,
                        (SELECT COUNT(*) FROM core.company_overview ov WHERE ov.symbol = s.symbol) as ov_cnt,
                        (SELECT COUNT(*) FROM core.company_shareholders sh WHERE sh.symbol = s.symbol) as sh_cnt
                    FROM (VALUES {values_str}) as s(symbol)
                """
                vn30_rows = con.execute(q_vn30).fetchall()
                for sym, o_c, f_c, n_c, e_c, fl_c, ov_c, sh_c in vn30_rows:
                    covered_dims = sum([1 for c in [o_c, f_c, n_c, e_c, fl_c, ov_c, sh_c] if c > 0])
                    report["vn30_coverage"][sym] = {
                        "ohlcv": o_c,
                        "fundamentals": f_c,
                        "news": n_c,
                        "events": e_c,
                        "prop_flow": fl_c,
                        "overview": ov_c,
                        "shareholders": sh_c,
                        "completion_pct": round(covered_dims / 7.0 * 100, 1),
                    }
            except Exception as ex:
                logger.debug("Lỗi kiểm tra VN30 coverage: %s", ex)

            # 4. Kiểm tra meta.crawl_progress
            try:
                q_jobs = """
                    SELECT status, COUNT(*) as cnt
                    FROM meta.crawl_progress
                    GROUP BY status
                """
                jobs_rows = con.execute(q_jobs).fetchall()
                report["jobs_summary"] = {r[0]: r[1] for r in jobs_rows}
            except Exception as ex:
                logger.debug("Lỗi lấy crawl_progress: %s", ex)

        finally:
            con.close()

        return report

    def render_terminal(self, report: Dict[str, Any]) -> None:
        """In toàn bộ bảng số liệu ra terminal dạng Dashboard chuyên nghiệp."""
        os.system("cls" if os.name == "nt" else "clear")
        # 1. Header
        print("\n" + "╔" + "═" * 108 + "╗")
        print(f"║ {'VESTA QUANTITATIVE LAKEHOUSE & CRAWLER PROGRESS TRACKER':^106} ║")
        print("╠" + "═" * 108 + "╣")
        print(f"║ Thời điểm quét: {report['timestamp']}  | CSDL: {os.path.basename(report['db_path'])}  | Dung lượng: {report['db_size_mb']:,.2f} MB ║")
        print(f"║ Trạng thái kết nối: {report['connection_status']:<90} ║")
        print("╚" + "═" * 108 + "╝")

        # 2. Bảng Core Tables
        print("\n" + "┌" + "─" * 108 + "┐")
        print(f"│ {'1. TỔNG QUAN CƠ SỞ DỮ LIỆU CỐT LÕI (CORE TABLES INGESTION SUMMARY)':<106} │")
        print("├" + "─" * 32 + "┬" + "─" * 12 + "┬" + "─" * 12 + "┬" + "─" * 12 + "┬" + "─" * 12 + "┬" + "─" * 23 + "┤")
        print(f"│ {'Bảng Dữ Liệu':<30} │ {'Tổng Số Dòng':>10} │ {'Số Mã/Khóa':>10} │ {'Mốc Cũ Nhất':^10} │ {'Mốc Mới Nhất':^10} │ {'Độ Tươi/Trạng Thái':^21} │")
        print("├" + "─" * 32 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 23 + "┤")
        for t in report["tables"]:
            print(f"│ {t['table']:<30} │ {t['records']:>10,d} │ {t['unique_keys']:>10,d} │ {t['min_date']:^10} │ {t['max_date']:^10} │ {t['freshness']:<21} │")
        print("└" + "─" * 32 + "┴" + "─" * 12 + "┴" + "─" * 12 + "┴" + "─" * 12 + "┴" + "─" * 12 + "┴" + "─" * 23 + "┘")

        # 3. Phân rã News & Policy Sources
        print("\n" + "┌" + "─" * 108 + "┐")
        print(f"│ {'2. ĐÁNH GIÁ ĐỘ PHỦ THEO NGUỒN TIN TỨC & CHÍNH SÁCH (NEWS & POLICY SOURCES COVERAGE)':<106} │")
        print("├" + "─" * 24 + "┬" + "─" * 24 + "┬" + "─" * 12 + "┬" + "─" * 12 + "┬" + "─" * 12 + "┬" + "─" * 18 + "┤")
        print(f"│ {'Danh mục':<22} │ {'Tên Nguồn/Cơ quan':<22} │ {'Số Bài Viết':>10} │ {'Tin Cũ Nhất':^10} │ {'Tin Mới Nhất':^10} │ {'Độ Phủ 2000-Nay':^16} │")
        print("├" + "─" * 24 + "┼" + "─" * 24 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 12 + "┼" + "─" * 18 + "┤")
        for s in report["news_sources"]:
            span = f"{s['backward_gap']} | {s['forward_gap']}"
            print(f"│ {s['category']:<22} │ {s['source']:<22} │ {s['total_articles']:>10,d} │ {s['min_date']:^10} │ {s['max_date']:^10} │ {span[:16]:^16} │")
        print("└" + "─" * 24 + "┴" + "─" * 24 + "┴" + "─" * 12 + "┴" + "─" * 12 + "┴" + "─" * 12 + "┴" + "─" * 18 + "┘")

        # 4. Độ phủ VN30 7 chiều
        print("\n" + "┌" + "─" * 108 + "┐")
        print(f"│ {'3. MA TRẬN ĐỘ PHỦ 7 CHIỀU CỦA RỔ VN30 (OHLCV, BCTC, TIN TỨC, SỰ KIỆN, TỰ DOANH, HỒ SƠ, CỔ ĐÔNG)':<106} │")
        print("├" + "─" * 108 + "┤")
        completed_vn30 = [sym for sym, d in report["vn30_coverage"].items() if d["completion_pct"] >= 100.0]
        partial_vn30 = [sym for sym, d in report["vn30_coverage"].items() if d["completion_pct"] < 100.0]
        print(f"│  • ĐÃ HOÀN TẤT ĐỦ 5/5 CHIỀU ({len(completed_vn30)}/30 mã):")
        print(f"│    {', '.join(completed_vn30[:15])}")
        if len(completed_vn30) > 15:
            print(f"│    {', '.join(completed_vn30[15:])}")
        if partial_vn30:
            print(f"│  • CẦN NẠP BỔ SUNG ({len(partial_vn30)} mã): {', '.join(partial_vn30)}")
        print("└" + "─" * 108 + "┘")

        # 4. Hàng đợi crawl_progress
        print("\n" + "┌" + "─" * 108 + "┐")
        print(f"│ {'4. TRẠNG THÁI TIẾN TRÌNH CÀO (META.CRAWL_PROGRESS)':<106} │")
        print("├" + "─" * 108 + "┤")
        jobs = report["jobs_summary"]
        print(f"│  Thành công (success): {jobs.get('success', 0):>6,d} | Rỗng (empty): {jobs.get('empty', 0):>6,d} | Thất bại (failed): {jobs.get('failed', 0):>6,d} | Chờ xử lý: {jobs.get('pending', 0):>6,d} │")
        print("└" + "─" * 108 + "┘\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VESTA Real-Time Crawling & Lakehouse Progress Tracker")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Đường dẫn file DuckDB cần kiểm tra")
    parser.add_argument("--watch", type=int, default=0, help="Tần suất tự động làm mới màn hình (giây, 0 = chạy 1 lần)")
    parser.add_argument("--json", action="store_true", help="Xuất kết quả dưới định dạng JSON")
    parser.add_argument("--export", default="", help="Xuất báo cáo JSON ra tệp chỉ định")
    return parser.parse_args()


def run_progress_tracker(duckdb_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Hàm tiện ích chạy kiểm toán và render terminal trực tiếp."""
    tracker = CrawlingProgressTracker(db_path=duckdb_path)
    rep = tracker.generate_report()
    tracker.render_terminal(rep)
    return rep


def main() -> int:
    args = parse_args()
    tracker = CrawlingProgressTracker(db_path=args.db)

    if args.watch > 0:
        logger.info("Bắt đầu chế độ giám sát thời gian thực (làm mới mỗi %d giây)...", args.watch)
        try:
            while True:
                rep = tracker.generate_report()
                tracker.render_terminal(rep)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nĐã dừng giám sát tiến độ.")
            return 0

    report = tracker.generate_report()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.export:
        out_path = os.path.abspath(args.export)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"Đã xuất báo cáo tiến độ ra: {out_path}")

    tracker.render_terminal(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
