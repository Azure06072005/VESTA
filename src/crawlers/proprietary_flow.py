"""src/crawlers/proprietary_flow.py

Crawler for proprietary desk trading flows (Tự doanh) per symbol on HOSE/HNX/UPCOM.
Utilizes the official Vnstock 3.3.0+ Unified API (Silver Sponsor Tier).

Data captured:
- Buy / Sell Volume & Value (Khối lượng / Giá trị Mua & Bán)
- Net Volume & Net Value (Khối lượng / Giá trị Mua ròng)
- Date range: Recent sessions per ticker

Destination:
- staging.proprietary_flow (Raw intake)
- core.proprietary_flow (Promoted & deduplicated on symbol + date)
- meta.crawl_progress (Job execution status tracking)
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawlers.proprietary_flow")

VN30_SYMBOLS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]


class ProprietaryFlowCrawler:
    """Crawler thu thập dữ liệu giao dịch tự doanh chi tiết từng mã từ Vnstock."""

    def __init__(
        self,
        db_path: str | Path = "db/vesta.duckdb",
        api_key: Optional[str] = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.api_key = api_key or os.environ.get(
            "VNSTOCK_API_KEY", "vnstock_f84ed9f3014e77c53a88e3eae1bc1be8"
        )
        os.environ["VNSTOCK_API_KEY"] = self.api_key

        from vnstock_data import Market
        self.market = Market()
        self._init_tables()

    def _init_tables(self) -> None:
        """Đảm bảo các bảng staging, core và meta tồn tại."""
        con = duckdb.connect(str(self.db_path), read_only=False)
        try:
            con.execute("CREATE SCHEMA IF NOT EXISTS staging;")
            con.execute("CREATE SCHEMA IF NOT EXISTS core;")
            con.execute("CREATE SCHEMA IF NOT EXISTS meta;")

            con.execute("""
                CREATE TABLE IF NOT EXISTS meta.crawl_progress (
                    dataset_name  VARCHAR NOT NULL,
                    symbol        VARCHAR NOT NULL,
                    status        VARCHAR NOT NULL,
                    retry_count   INTEGER NOT NULL DEFAULT 0,
                    last_attempt  TIMESTAMP,
                    PRIMARY KEY (dataset_name, symbol)
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS staging.proprietary_flow (
                    symbol        VARCHAR NOT NULL,
                    date          DATE NOT NULL,
                    buy_vol       DOUBLE,
                    buy_val       DOUBLE,
                    sell_vol      DOUBLE,
                    sell_val      DOUBLE,
                    net_vol       DOUBLE,
                    net_val       DOUBLE,
                    fetched_at    TIMESTAMP NOT NULL
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS core.proprietary_flow (
                    symbol        VARCHAR NOT NULL,
                    date          DATE NOT NULL,
                    buy_vol       DOUBLE,
                    buy_val       DOUBLE,
                    sell_vol      DOUBLE,
                    sell_val      DOUBLE,
                    net_vol       DOUBLE,
                    net_val       DOUBLE,
                    fetched_at    TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, date)
                );
            """)
        finally:
            con.close()

    def fetch_symbol_data(self, symbol: str) -> pd.DataFrame:
        """Lấy dữ liệu tự doanh từ Vnstock cho 1 mã cổ phiếu."""
        sym = symbol.strip().upper()
        try:
            df = self.market.equity(sym).proprietary_flow()
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                logger.warning(f"[{sym}] Không có dữ liệu tự doanh hoặc trả về rỗng.")
                return pd.DataFrame()

            # Chuẩn hóa tên cột: time, buy_vol, buy_val, sell_vol, sell_val, net_vol, net_val
            clean_df = pd.DataFrame()
            clean_df["symbol"] = [sym] * len(df)
            clean_df["date"] = pd.to_datetime(df["time"]).dt.date
            clean_df["buy_vol"] = pd.to_numeric(df.get("buy_vol"), errors="coerce")
            clean_df["buy_val"] = pd.to_numeric(df.get("buy_val"), errors="coerce")
            clean_df["sell_vol"] = pd.to_numeric(df.get("sell_vol"), errors="coerce")
            clean_df["sell_val"] = pd.to_numeric(df.get("sell_val"), errors="coerce")
            clean_df["net_vol"] = pd.to_numeric(df.get("net_vol"), errors="coerce")
            clean_df["net_val"] = pd.to_numeric(df.get("net_val"), errors="coerce")
            clean_df["fetched_at"] = pd.Timestamp.now()

            # Loại bỏ bản ghi trùng ngày
            clean_df = clean_df.dropna(subset=["date"]).drop_duplicates(subset=["symbol", "date"])
            return clean_df

        except Exception as e:
            logger.error(f"[{sym}] Lỗi khi gọi vnstock proprietary_flow: {e}")
            raise

    def save_and_promote(self, df: pd.DataFrame, symbol: str) -> int:
        """Lưu dữ liệu vào staging và upsert sang core."""
        if df.empty:
            return 0

        con = duckdb.connect(str(self.db_path), read_only=False)
        try:
            # 1. Ghi vào staging
            con.register("df_temp_staging", df)
            con.execute("INSERT INTO staging.proprietary_flow SELECT * FROM df_temp_staging;")

            # 2. Promoted vào core (Idempotent: Upsert dựa trên symbol, date)
            con.execute("""
                INSERT INTO core.proprietary_flow
                SELECT 
                    symbol, date, buy_vol, buy_val, sell_vol, sell_val, net_vol, net_val, fetched_at
                FROM df_temp_staging
                ON CONFLICT (symbol, date) DO UPDATE SET
                    buy_vol = EXCLUDED.buy_vol,
                    buy_val = EXCLUDED.buy_val,
                    sell_vol = EXCLUDED.sell_vol,
                    sell_val = EXCLUDED.sell_val,
                    net_vol = EXCLUDED.net_vol,
                    net_val = EXCLUDED.net_val,
                    fetched_at = EXCLUDED.fetched_at;
            """)

            # 3. Cập nhật meta.crawl_progress
            now_ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute(f"""
                INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
                VALUES ('proprietary_flow', '{symbol}', 'success', 0, '{now_ts}')
                ON CONFLICT (dataset_name, symbol) DO UPDATE SET
                    status = 'success',
                    last_attempt = '{now_ts}';
            """)
            return len(df)
        finally:
            con.close()

    def record_failure(self, symbol: str, status: str = "failed") -> None:
        """Ghi nhận lỗi hoặc dữ liệu rỗng vào meta.crawl_progress."""
        now_ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con = duckdb.connect(str(self.db_path), read_only=False)
        try:
            con.execute(f"""
                INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
                VALUES ('proprietary_flow', '{symbol}', '{status}', 1, '{now_ts}')
                ON CONFLICT (dataset_name, symbol) DO UPDATE SET
                    status = '{status}',
                    retry_count = meta.crawl_progress.retry_count + 1,
                    last_attempt = '{now_ts}';
            """)
        finally:
            con.close()

    def get_all_market_symbols(self) -> List[str]:
        """Lấy toàn bộ danh sách mã cổ phiếu đang niêm yết trong CSDL."""
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            df = con.execute("""
                SELECT symbol FROM core.dim_symbol 
                WHERE is_delisted IS FALSE OR is_delisted IS NULL
                ORDER BY symbol
            """).df()
            return df["symbol"].tolist()
        except Exception:
            return VN30_SYMBOLS
        finally:
            con.close()

    def crawl_symbol(self, symbol: str) -> int:
        """Cào và nạp dữ liệu giao dịch tự doanh cho 1 mã cổ phiếu."""
        sym = symbol.strip().upper()
        try:
            df = self.fetch_symbol_data(sym)
            if df.empty:
                self.record_failure(sym, status="empty")
                return 0
            return self.save_and_promote(df, sym)
        except Exception as e:
            logger.error(f" -> [{sym}] Thất bại cào tự doanh: {e}")
            self.record_failure(sym, status="failed")
            return 0

    def run(self, symbols: List[str], delay_sec: float = 0.5) -> Dict[str, Any]:
        """Thực thi cào dữ liệu cho danh sách mã chỉ định."""
        total = len(symbols)
        success_count = 0
        total_rows = 0

        logger.info(f"Bắt đầu cào tự doanh cho {total} mã cổ phiếu vào CSDL {self.db_path}...")

        for idx, sym in enumerate(symbols, start=1):
            logger.info(f"[{idx}/{total}] Đang xử lý mã: {sym}...")
            try:
                df = self.fetch_symbol_data(sym)
                if df.empty:
                    self.record_failure(sym, status="empty")
                else:
                    rows = self.save_and_promote(df, sym)
                    total_rows += rows
                    success_count += 1
                    logger.info(f" -> [{sym}] Đã nạp thành công {rows} phiên giao dịch tự doanh.")
            except Exception as e:
                logger.error(f" -> [{sym}] Thất bại: {e}")
                self.record_failure(sym, status="failed")

            time.sleep(delay_sec)

        logger.info(f"Hoàn tất cào dữ liệu tự doanh: {success_count}/{total} thành công, tổng cộng {total_rows} dòng.")
        return {
            "total_symbols": total,
            "success_symbols": success_count,
            "total_rows_promoted": total_rows,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA Proprietary Trading Flow Crawler (Vnstock 3.3.0)")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated ticker list (e.g. VCB,TCB,MBB)")
    parser.add_argument("--all-symbols", action="store_true", help="Cào toàn bộ mã cổ phiếu niêm yết trên thị trường")
    parser.add_argument("--db-path", type=str, default="db/vesta.duckdb", help="Path to DuckDB database")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of symbols to crawl")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between symbol requests in seconds")
    args = parser.parse_args()

    crawler = ProprietaryFlowCrawler(db_path=args.db_path)

    if args.all_symbols:
        symbol_list = crawler.get_all_market_symbols()
    elif args.symbols:
        symbol_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbol_list = VN30_SYMBOLS

    if args.limit > 0:
        symbol_list = symbol_list[: args.limit]
    res = crawler.run(symbol_list, delay_sec=args.delay)
    print("\n[CRAWL RESULT SUMMARY]")
    for k, v in res.items():
        print(f" - {k}: {v}")


if __name__ == "__main__":
    main()
