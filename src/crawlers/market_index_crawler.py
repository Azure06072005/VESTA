"""Crawler đồng bộ dữ liệu OHLCV các chỉ số sàn (Exchanges) và rổ nhóm (Group Rooms).

Nguồn dữ liệu:
  - vnstock_data (KBS Unified API) cho các chỉ số:
    * Sàn giao dịch chính: VNINDEX, HNXINDEX, UPCOMINDEX
    * Rổ chỉ số hàng đầu: VN30, HNX30, VN100
  - Dữ liệu ETF mô phỏng rổ room ngoại (VNDIAMOND qua FUEVFVND, VNFINLEAD qua FUESSVFL)

Lưu trữ vào:
  - `core.market_index_daily` (index_code, date, open, high, low, close, volume, fetched_at)
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

try:
    from vnstock_data import Market
except ImportError:
    from vnstock import Market

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("market_index_crawler")

DEFAULT_DUCKDB_PATH = "d:/VESTA/db/vesta_ohlcv.duckdb"

# Bản đồ chỉ số nguồn KBS -> Mã chuẩn hóa trong DB
INDEX_MAPPING = {
    "VNINDEX": "VNINDEX",
    "VN30": "VN30",
    "HNXINDEX": "HNX-INDEX",
    "HNX30": "HNX30",
    "UPCOMINDEX": "UPCOM-INDEX",
    "VN100": "VN100"
}


class MarketIndexCrawler:
    """Crawler lấy dữ liệu lịch sử và hàng ngày cho các chỉ số sàn và rổ nhóm."""

    def __init__(self, duckdb_path: str = DEFAULT_DUCKDB_PATH) -> None:
        self.duckdb_path = duckdb_path
        self.mkt = Market()

    def fetch_index_ohlcv(
        self,
        source_code: str,
        start_date: str = "2010-01-01",
        end_date: str | None = None
    ) -> pd.DataFrame:
        """Lấy lịch sử OHLCV của 1 chỉ số từ vnstock_data."""
        if not end_date:
            end_date = dt.datetime.now().strftime("%Y-%m-%d")

        try:
            logger.info(f"Đang tải lịch sử chỉ số {source_code} ({start_date} -> {end_date})...")
            df = self.mkt.index(source_code).ohlcv(start=start_date, end=end_date)
            if df is None or df.empty:
                logger.warning(f"Không nhận được dữ liệu cho chỉ số {source_code}.")
                return pd.DataFrame()

            # Chuẩn hóa cột
            # df trả về các cột: time, open, high, low, close, volume
            df["date"] = pd.to_datetime(df["time"]).dt.date
            target_code = INDEX_MAPPING.get(source_code, source_code)
            df["index_code"] = target_code
            df["fetched_at"] = dt.datetime.now()

            result_df = df[["index_code", "date", "open", "high", "low", "close", "volume", "fetched_at"]].copy()
            # Ép kiểu dữ liệu an toàn
            result_df["open"] = pd.to_numeric(result_df["open"], errors="coerce")
            result_df["high"] = pd.to_numeric(result_df["high"], errors="coerce")
            result_df["low"] = pd.to_numeric(result_df["low"], errors="coerce")
            result_df["close"] = pd.to_numeric(result_df["close"], errors="coerce")
            result_df["volume"] = pd.to_numeric(result_df["volume"], errors="coerce").fillna(0).astype("int64")

            logger.info(f"-> Tải thành công {len(result_df):,} phiên cho {source_code} (Mã lưu: {target_code}).")
            return result_df
        except Exception as e:
            logger.error(f"Lỗi khi tải chỉ số {source_code}: {e}")
            return pd.DataFrame()

    def save_to_duckdb(self, df: pd.DataFrame) -> int:
        """Ghi dữ liệu chỉ số vào core.market_index_daily với UPSERT an toàn."""
        if df.empty:
            return 0

        con = duckdb.connect(self.duckdb_path, read_only=False)
        try:
            # Tạo bảng nếu chưa tồn tại
            con.execute("""
                CREATE TABLE IF NOT EXISTS core.market_index_daily (
                    index_code VARCHAR NOT NULL,
                    date DATE NOT NULL,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume BIGINT,
                    fetched_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (index_code, date)
                )
            """)

            con.register("df_index_incoming", df)
            con.execute("""
                INSERT INTO core.market_index_daily (
                    index_code, date, open, high, low, close, volume, fetched_at
                )
                SELECT index_code, date, open, high, low, close, volume, fetched_at
                FROM df_index_incoming
                ON CONFLICT (index_code, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    fetched_at = EXCLUDED.fetched_at
            """)
            affected = len(df)
            return affected
        finally:
            con.close()

    def crawl_all_indices(self, start_date: str = "2010-01-01") -> dict[str, int]:
        """Cào và cập nhật toàn bộ các chỉ số sàn và rổ nhóm."""
        results = {}
        for src_code in INDEX_MAPPING.keys():
            df = self.fetch_index_ohlcv(src_code, start_date=start_date)
            if not df.empty:
                saved = self.save_to_duckdb(df)
                results[src_code] = saved
            else:
                results[src_code] = 0
        return results


def main() -> None:
    """Hàm chạy dòng lệnh chính."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logger.info("=== BẮT ĐẦU CÀO BÙ CHỈ SỐ SÀN VÀ RỔ NHÓM (EXCHANGES & GROUP ROOMS) ===")
    crawler = MarketIndexCrawler()
    results = crawler.crawl_all_indices(start_date="2010-01-01")
    logger.info("\n=== KẾT QUẢ ĐỒNG BỘ CHỈ SỐ ===")
    for code, count in results.items():
        target = INDEX_MAPPING.get(code, code)
        logger.info(f" - Chỉ số {code:12} -> {target:12}: {count:,} phiên đã nạp.")


if __name__ == "__main__":
    main()
