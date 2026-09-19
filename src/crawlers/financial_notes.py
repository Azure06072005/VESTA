"""src/crawlers/financial_notes.py

Deep Financial Statement Notes Crawler (Thuyết minh BCTC chuyên sâu).
Utilizes the official Vnstock 3.3.0+ Unified API (Silver Sponsor Tier).

Extracts granular accounting breakdowns per symbol:
- Corporate bond holdings & debt securities (Cơ cấu danh mục trái phiếu DN)
- Non-performing loans (NPL groups 2-5: Nợ cần chú ý đến nợ có khả năng mất vốn)
- Loan loss provisions & credit risk reserves (Trích lập dự phòng rủi ro)
- Real estate development inventory & project capex breakdown

Destination:
- staging.financial_notes (Raw intake)
- core.financial_notes (Promoted & deduplicated on symbol + period + note_id)
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
logger = logging.getLogger("crawlers.financial_notes")

KEY_FINANCIAL_SYMBOLS = [
    # Top banks with heavy credit / NPL exposure
    "VCB", "TCB", "MBB", "VPB", "BID", "CTG", "ACB", "HDB", "STB", "SHB",
    # Top real estate developers with heavy bond / debt exposure
    "VHM", "NVL", "VIC", "VRE", "PDR", "DXG", "KDH", "DIG", "NLG", "KBC",
]


class FinancialNotesCrawler:
    """Crawler trích xuất thuyết minh báo cáo tài chính phân rã chi tiết từ Vnstock."""

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

        from vnstock_data import Fundamental
        self.fundamental = Fundamental()
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
                CREATE TABLE IF NOT EXISTS staging.financial_notes (
                    symbol        VARCHAR NOT NULL,
                    period        VARCHAR NOT NULL,
                    note_id       VARCHAR NOT NULL,
                    note_name     VARCHAR,
                    item_order    INTEGER,
                    item_level    INTEGER,
                    unit          VARCHAR,
                    value         DOUBLE,
                    fetched_at    TIMESTAMP NOT NULL
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS core.financial_notes (
                    symbol        VARCHAR NOT NULL,
                    period        VARCHAR NOT NULL,
                    note_id       VARCHAR NOT NULL,
                    note_name     VARCHAR,
                    item_order    INTEGER,
                    item_level    INTEGER,
                    unit          VARCHAR,
                    value         DOUBLE,
                    fetched_at    TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, period, note_id)
                );
            """)
        finally:
            con.close()

    def fetch_symbol_notes(self, symbol: str) -> pd.DataFrame:
        """Lấy toàn bộ thuyết minh BCTC từ vnstock cho 1 mã."""
        sym = symbol.strip().upper()
        try:
            df = self.fundamental.equity(sym).note()
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                logger.warning(f"[{sym}] Không có dữ liệu thuyết minh BCTC hoặc trả về rỗng.")
                return pd.DataFrame()

            # Columns in vnstock: ['period', 'id', 'name', 'order', 'level', 'unit', 'value']
            clean_df = pd.DataFrame()
            clean_df["symbol"] = [sym] * len(df)
            clean_df["period"] = df["period"].astype(str)
            clean_df["note_id"] = df["id"].astype(str)
            clean_df["note_name"] = df["name"].astype(str)
            clean_df["item_order"] = pd.to_numeric(df.get("order"), errors="coerce").fillna(0).astype(int)
            clean_df["item_level"] = pd.to_numeric(df.get("level"), errors="coerce").fillna(0).astype(int)
            clean_df["unit"] = df.get("unit", "VNĐ").astype(str)
            clean_df["value"] = pd.to_numeric(df["value"], errors="coerce")
            clean_df["fetched_at"] = pd.Timestamp.now()

            clean_df = clean_df.dropna(subset=["period", "note_id"]).drop_duplicates(
                subset=["symbol", "period", "note_id"]
            )
            return clean_df

        except Exception as e:
            logger.error(f"[{sym}] Lỗi khi gọi vnstock fundamental note: {e}")
            raise

    def save_and_promote(self, df: pd.DataFrame, symbol: str) -> int:
        """Lưu dữ liệu thuyết minh vào staging và upsert sang core."""
        if df.empty:
            return 0

        con = duckdb.connect(str(self.db_path), read_only=False)
        try:
            # 1. Ghi vào staging
            con.register("df_notes_staging", df)
            con.execute("INSERT INTO staging.financial_notes SELECT * FROM df_notes_staging;")

            # 2. Promoted vào core (Idempotent: Upsert dựa trên symbol, period, note_id)
            con.execute("""
                INSERT INTO core.financial_notes
                SELECT 
                    symbol, period, note_id, note_name, item_order, item_level, unit, value, fetched_at
                FROM df_notes_staging
                ON CONFLICT (symbol, period, note_id) DO UPDATE SET
                    note_name = EXCLUDED.note_name,
                    item_order = EXCLUDED.item_order,
                    item_level = EXCLUDED.item_level,
                    unit = EXCLUDED.unit,
                    value = EXCLUDED.value,
                    fetched_at = EXCLUDED.fetched_at;
            """)

            # 3. Cập nhật meta.crawl_progress
            now_ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute(f"""
                INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
                VALUES ('financial_notes', '{symbol}', 'success', 0, '{now_ts}')
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
                VALUES ('financial_notes', '{symbol}', '{status}', 1, '{now_ts}')
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
            return KEY_FINANCIAL_SYMBOLS
        finally:
            con.close()

    def crawl_symbol(self, symbol: str) -> int:
        """Cào và nạp thuyết minh BCTC cho 1 mã cổ phiếu."""
        sym = symbol.strip().upper()
        try:
            df = self.fetch_symbol_notes(sym)
            if df.empty:
                self.record_failure(sym, status="empty")
                return 0
            return self.save_and_promote(df, sym)
        except Exception as e:
            logger.error(f" -> [{sym}] Thất bại cào thuyết minh: {e}")
            self.record_failure(sym, status="failed")
            return 0

    def run(self, symbols: List[str], delay_sec: float = 1.0) -> Dict[str, Any]:
        """Thực thi cào thuyết minh BCTC cho danh sách mã chỉ định."""
        total = len(symbols)
        success_count = 0
        total_rows = 0

        logger.info(f"Bắt đầu cào Thuyết minh BCTC cho {total} mã vào CSDL {self.db_path}...")

        for idx, sym in enumerate(symbols, start=1):
            logger.info(f"[{idx}/{total}] Đang trích xuất Thuyết minh BCTC: {sym}...")
            try:
                df = self.fetch_symbol_notes(sym)
                if df.empty:
                    self.record_failure(sym, status="empty")
                else:
                    rows = self.save_and_promote(df, sym)
                    total_rows += rows
                    success_count += 1
                    logger.info(f" -> [{sym}] Đã nạp thành công {rows} khoản mục thuyết minh BCTC.")
            except Exception as e:
                logger.error(f" -> [{sym}] Thất bại: {e}")
                self.record_failure(sym, status="failed")

            time.sleep(delay_sec)

        logger.info(f"Hoàn tất cào Thuyết minh BCTC: {success_count}/{total} thành công, tổng cộng {total_rows} dòng.")
        return {
            "total_symbols": total,
            "success_symbols": success_count,
            "total_rows_promoted": total_rows,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA Deep Financial Notes Crawler (Vnstock 3.3.0)")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated ticker list (e.g. VCB,TCB,MBB,VHM)")
    parser.add_argument("--all-symbols", action="store_true", help="Cào toàn bộ mã cổ phiếu trên thị trường")
    parser.add_argument("--db-path", type=str, default="db/vesta.duckdb", help="Path to DuckDB database")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of symbols to crawl")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between symbol requests in seconds")
    args = parser.parse_args()

    crawler = FinancialNotesCrawler(db_path=args.db_path)

    if args.all_symbols:
        symbol_list = crawler.get_all_market_symbols()
    elif args.symbols:
        symbol_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbol_list = KEY_FINANCIAL_SYMBOLS

    if args.limit > 0:
        symbol_list = symbol_list[: args.limit]

    res = crawler.run(symbol_list, delay_sec=args.delay)
    print("\n[FINANCIAL NOTES CRAWL RESULT SUMMARY]")
    for k, v in res.items():
        print(f" - {k}: {v}")


if __name__ == "__main__":
    main()
