"""src/crawlers/boundary_manager.py

VESTA Boundary & Coverage Manager.
Quản lý phạm vi thời gian (Date Boundaries), kiểm tra dữ liệu đã tồn tại và cơ chế Bỏ Qua (Skip):
1. Symbol-level Skip: Kiểm tra mã cổ phiếu đã có đủ dữ liệu trong database chưa. Nếu đã có -> Bỏ qua.
2. Date-boundary Analysis:
   - Nếu dữ liệu mới chỉ có trong khoảng (ví dụ: 2020 - 2026):
     - Giai đoạn 1 (Ưu tiên số 1 - Forward Catchup): Cào từ Max Date đến Hôm nay (2026 - nay).
     - Giai đoạn 2 (Ưu tiên số 2 - Backward Backfill): Cào từ Min Date lùi về 2000 (hoặc inception).
     - Giai đoạn 3: Bỏ qua hoàn toàn dải ngày 2020 - 2026 đã có sẵn trong database.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import duckdb
import pandas as pd

logger = logging.getLogger("boundary_manager")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = str(PROJECT_ROOT / "db" / "vesta_snapshot.duckdb")


class BoundaryManager:
    """Bộ điều phối biên ngày tháng và kiểm tra trùng lặp dữ liệu trước khi cào."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = os.path.abspath(db_path)

    def _get_connection(self) -> Optional[duckdb.DuckDBPyConnection]:
        """Lấy kết nối đọc an toàn tới DuckDB."""
        try:
            return duckdb.connect(self.db_path, read_only=True)
        except Exception as e:
            logger.debug("Không thể mở kết nối read_only tới %s: %s", self.db_path, e)
            # Thử file dự phòng fresh nếu có
            buf = os.path.abspath(str(PROJECT_ROOT / "db" / "vesta_crawled_fresh.duckdb"))
            if os.path.exists(buf):
                try:
                    return duckdb.connect(buf, read_only=True)
                except Exception:
                    pass
            return None

    def audit_symbol_coverage(
        self,
        table_name: str,
        symbols: List[str],
        date_column: str = "fetched_at",
    ) -> Dict[str, Dict[str, Any]]:
        """Kiểm tra độ phủ dữ liệu của từng mã cổ phiếu trong bảng chỉ định."""
        res: Dict[str, Dict[str, Any]] = {
            s.upper(): {"has_data": False, "count": 0, "min_date": None, "max_date": None}
            for s in symbols
        }

        con = self._get_connection()
        if not con:
            return res

        try:
            sym_list = "', '".join([s.upper() for s in symbols])
            query = f"""
                SELECT 
                    upper(symbol) as symbol,
                    COUNT(*) as cnt,
                    MIN({date_column}) as min_d,
                    MAX({date_column}) as max_d
                FROM core.{table_name}
                WHERE upper(symbol) IN ('{sym_list}')
                GROUP BY symbol
            """
            rows = con.execute(query).fetchall()
            for sym, cnt, min_d, max_d in rows:
                res[sym] = {
                    "has_data": cnt > 0,
                    "count": cnt,
                    "min_date": str(min_d)[:10] if min_d else None,
                    "max_date": str(max_d)[:10] if max_d else None,
                }
        except Exception as e:
            logger.debug("Lỗi audit symbol coverage trên core.%s: %s", table_name, e)
        finally:
            con.close()

        return res

    def filter_symbols_to_crawl(
        self,
        table_name: str,
        symbols: List[str],
        force: bool = False,
        min_records_threshold: int = 1,
        date_column: str = "fetched_at",
    ) -> Tuple[List[str], List[str]]:
        """Lọc danh sách mã cần cào và mã được bỏ qua do đã có dữ liệu.

        Returns:
            (symbols_to_crawl, symbols_skipped)
        """
        if force:
            logger.info("Cờ --force được bật: Bỏ qua kiểm tra độ phủ, cào toàn bộ %d mã.", len(symbols))
            return symbols, []

        coverage = self.audit_symbol_coverage(table_name, symbols, date_column=date_column)
        to_crawl: List[str] = []
        skipped: List[str] = []

        for sym, stat in coverage.items():
            if stat["has_data"] and stat["count"] >= min_records_threshold:
                skipped.append(sym)
                logger.info(
                    "  -> [BỎ QUA - ĐÃ CÓ DỮ LIỆU] %s trong core.%s (+%d bản ghi: %s -> %s)",
                    sym,
                    table_name,
                    stat["count"],
                    stat["min_date"],
                    stat["max_date"],
                )
            else:
                to_crawl.append(sym)

        if skipped:
            logger.info(
                "Đã tự động bỏ qua %d/%d mã đã có dữ liệu trong core.%s. Cần cào %d mã mới.",
                len(skipped),
                len(symbols),
                table_name,
                len(to_crawl),
            )

        return to_crawl, skipped

    def audit_source_date_boundary(
        self,
        table_name: str,
        source_name: str,
        date_column: str = "published_at",
        target_earliest_year: int = 2000,
    ) -> Dict[str, Any]:
        """Phân tích biên ngày tháng của nguồn tin tức (Kiểm tra khoảng trống tiến và lùi)."""
        now = dt.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        earliest_target = f"{target_earliest_year}-01-01"

        res = {
            "source": source_name,
            "table": f"core.{table_name}",
            "total_records": 0,
            "min_date": None,
            "max_date": None,
            "forward_gap": None,   # Khoảng ngày cần cào tiến đến hôm nay (Priority 1)
            "backward_gap": None,  # Khoảng ngày cần cào lùi về 2000 (Priority 2)
            "already_covered_range": None, # Dải ngày đã có sẵn -> BỎ QUA
        }

        con = self._get_connection()
        if not con:
            res["forward_gap"] = (earliest_target, today_str)
            return res

        try:
            query = f"""
                SELECT 
                    COUNT(*) as cnt,
                    MIN({date_column}) as min_d,
                    MAX({date_column}) as max_d
                FROM core.{table_name}
                WHERE lower(source) = '{source_name.lower()}'
            """
            row = con.execute(query).fetchone()
            if row and row[0] > 0:
                cnt, min_d, max_d = row
                min_str = str(min_d)[:10]
                max_str = str(max_d)[:10]
                res["total_records"] = cnt
                res["min_date"] = min_str
                res["max_date"] = max_str
                res["already_covered_range"] = (min_str, max_str)

                # 1. Kiểm tra biên TIẾN (Ưu tiên cập nhật mới nhất: max_date -> Hôm nay)
                if max_str < today_str:
                    res["forward_gap"] = (max_str, today_str)

                # 2. Kiểm tra biên LÙI (Vét cạn lịch sử: 2000 -> min_date)
                if min_str > earliest_target:
                    res["backward_gap"] = (earliest_target, min_str)
            else:
                # Chưa có dữ liệu nào: Cần cào toàn bộ từ 2000 đến hôm nay
                res["forward_gap"] = (earliest_target, today_str)
        except Exception as e:
            logger.debug("Lỗi audit date boundary cho %s: %s", source_name, e)
            res["forward_gap"] = (earliest_target, today_str)
        finally:
            con.close()

        return res

    def print_crawling_strategy(self, boundary: Dict[str, Any]) -> None:
        """In ra chiến lược cào dữ liệu tối ưu theo thứ tự ưu tiên."""
        logger.info("=" * 70)
        logger.info("CHIẾN LƯỢC CÀO BIÊN NGÀY CHO NGUỒN: %s (%s)", boundary["source"].upper(), boundary["table"])
        if boundary["already_covered_range"]:
            logger.info("  ✓ ĐÃ CÓ TRONG CSDL: %s -> %s (%d bài) -> [TỰ ĐỘNG BỎ QUA]", 
                        boundary["already_covered_range"][0], boundary["already_covered_range"][1], boundary["total_records"])
        
        if boundary["forward_gap"]:
            logger.info("  🔥 [ƯU TIÊN 1 - CÀO TIẾN ĐẾN HÔM NAY]: %s -> %s", 
                        boundary["forward_gap"][0], boundary["forward_gap"][1])
        else:
            logger.info("  ✓ BIÊN TIẾN: Đã cập nhật đầy đủ đến hôm nay.")

        if boundary["backward_gap"]:
            logger.info("  ⏳ [ƯU TIÊN 2 - VÉT CẠN LỊCH SỬ]: %s -> %s", 
                        boundary["backward_gap"][0], boundary["backward_gap"][1])
        else:
            logger.info("  ✓ BIÊN LÙI: Đã vét cạn lịch sử về mốc mốc năm 2000.")
        logger.info("=" * 70)
