"""src/crawlers/foreign_flow_intraday.py

Intraday Real-Time Foreign Flow & Foreign Ownership Room Crawler.
Utilizes Vnstock 3.3.0+ Unified API (Silver Sponsor Tier):
- `Market.equity(symbol).quote()`: Real-time session foreign buy/sell volume.
- `Market.equity(symbol).summary()`: Real-time foreign ownership percentage (foreign_ownership_pct).

Destination:
- `staging.foreign_flow_intraday` / `core.foreign_flow_intraday` (Realtime snapshots per timestamp)
- `staging.foreign_ownership_room` / `core.foreign_ownership_room` (Session-level ownership & room)
- `meta.crawl_progress` (Job execution tracking)
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawlers.foreign_flow_intraday")


class ForeignFlowIntradayCrawler:
    """Crawler dòng tiền khối ngoại realtime trong phiên và tỷ lệ sở hữu room ngoại."""

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
        """Đảm bảo các bảng dữ liệu dòng tiền khối ngoại tồn tại trong DuckDB."""
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

            # Bảng dòng tiền khối ngoại trong phiên theo từng mốc thời gian
            con.execute("""
                CREATE TABLE IF NOT EXISTS staging.foreign_flow_intraday (
                    symbol                 VARCHAR NOT NULL,
                    timestamp              TIMESTAMP NOT NULL,
                    foreign_buy_volume     DOUBLE,
                    foreign_sell_volume    DOUBLE,
                    foreign_net_volume     DOUBLE,
                    foreign_ownership_pct  DOUBLE,
                    close_price            DOUBLE,
                    fetched_at             TIMESTAMP NOT NULL
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS core.foreign_flow_intraday (
                    symbol                 VARCHAR NOT NULL,
                    timestamp              TIMESTAMP NOT NULL,
                    foreign_buy_volume     DOUBLE,
                    foreign_sell_volume    DOUBLE,
                    foreign_net_volume     DOUBLE,
                    foreign_ownership_pct  DOUBLE,
                    close_price            DOUBLE,
                    fetched_at             TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, timestamp)
                );
            """)

            # Bảng tỷ lệ sở hữu và room ngoại còn lại theo phiên
            con.execute("""
                CREATE TABLE IF NOT EXISTS staging.foreign_ownership_room (
                    symbol                 VARCHAR NOT NULL,
                    date                   DATE NOT NULL,
                    foreign_ownership_pct  DOUBLE,
                    foreign_buy_volume     DOUBLE,
                    foreign_sell_volume    DOUBLE,
                    foreign_net_volume     DOUBLE,
                    fetched_at             TIMESTAMP NOT NULL
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS core.foreign_ownership_room (
                    symbol                 VARCHAR NOT NULL,
                    date                   DATE NOT NULL,
                    foreign_ownership_pct  DOUBLE,
                    foreign_buy_volume     DOUBLE,
                    foreign_sell_volume    DOUBLE,
                    foreign_net_volume     DOUBLE,
                    fetched_at             TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, date)
                );
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
            return ["SSI", "VND", "VCI", "HCM", "SHS", "HPG", "FPT", "VCB", "MWG"]
        finally:
            con.close()

    def fetch_symbol_foreign(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Trích xuất khối ngoại mua/bán realtime và tỷ lệ sở hữu nước ngoài."""
        sym = symbol.strip().upper()
        try:
            quote_df = self.market.equity(sym).quote()
            summary_df = self.market.equity(sym).summary()

            now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            today = now.date()

            f_buy = 0.0
            f_sell = 0.0
            close_px = None
            if quote_df is not None and not quote_df.empty:
                f_buy = float(quote_df.get("foreign_buy_volume", [0])[0] or 0.0)
                f_sell = float(quote_df.get("foreign_sell_volume", [0])[0] or 0.0)
                if "close_price" in quote_df.columns:
                    close_px = float(quote_df["close_price"].iloc[0])

            f_own_pct = 0.0
            if summary_df is not None and not summary_df.empty:
                if "foreign_ownership_pct" in summary_df.columns:
                    f_own_pct = float(summary_df["foreign_ownership_pct"].iloc[0] or 0.0)

            f_net = f_buy - f_sell

            record = {
                "symbol": sym,
                "timestamp": now,
                "date": today,
                "foreign_buy_volume": f_buy,
                "foreign_sell_volume": f_sell,
                "foreign_net_volume": f_net,
                "foreign_ownership_pct": f_own_pct,
                "close_price": close_px,
                "fetched_at": now
            }
            return record
        except Exception as e:
            logger.warning(f"[{sym}] Không thể lấy dữ liệu khối ngoại: {e}")
            return None

    def save_and_promote(self, record: Dict[str, Any]) -> bool:
        """Lưu trữ và thăng hạng bản ghi khối ngoại vào DuckDB."""
        con = duckdb.connect(str(self.db_path), read_only=False)
        try:
            df_intraday = pd.DataFrame([{
                "symbol": record["symbol"],
                "timestamp": record["timestamp"],
                "foreign_buy_volume": record["foreign_buy_volume"],
                "foreign_sell_volume": record["foreign_sell_volume"],
                "foreign_net_volume": record["foreign_net_volume"],
                "foreign_ownership_pct": record["foreign_ownership_pct"],
                "close_price": record["close_price"],
                "fetched_at": record["fetched_at"]
            }])

            df_room = pd.DataFrame([{
                "symbol": record["symbol"],
                "date": record["date"],
                "foreign_ownership_pct": record["foreign_ownership_pct"],
                "foreign_buy_volume": record["foreign_buy_volume"],
                "foreign_sell_volume": record["foreign_sell_volume"],
                "foreign_net_volume": record["foreign_net_volume"],
                "fetched_at": record["fetched_at"]
            }])

            con.register("df_intra", df_intraday)
            con.execute("INSERT INTO staging.foreign_flow_intraday SELECT * FROM df_intra;")
            con.execute("""
                INSERT INTO core.foreign_flow_intraday 
                SELECT * FROM df_intra 
                ON CONFLICT (symbol, timestamp) DO NOTHING;
            """)
            con.unregister("df_intra")

            con.register("df_r", df_room)
            con.execute("INSERT INTO staging.foreign_ownership_room SELECT * FROM df_r;")
            con.execute("""
                INSERT INTO core.foreign_ownership_room 
                SELECT * FROM df_r 
                ON CONFLICT (symbol, date) DO UPDATE SET
                    foreign_ownership_pct = excluded.foreign_ownership_pct,
                    foreign_buy_volume = excluded.foreign_buy_volume,
                    foreign_sell_volume = excluded.foreign_sell_volume,
                    foreign_net_volume = excluded.foreign_net_volume,
                    fetched_at = excluded.fetched_at;
            """)
            con.unregister("df_r")

            con.execute("""
                INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
                VALUES ('foreign_flow_intraday', ?, 'success', 0, CURRENT_TIMESTAMP)
                ON CONFLICT (dataset_name, symbol) DO UPDATE SET
                    status = excluded.status,
                    last_attempt = excluded.last_attempt;
            """, [record["symbol"]])
            return True
        finally:
            con.close()

    def run(self, symbols: Optional[List[str]] = None, delay_sec: float = 0.4) -> Dict[str, Any]:
        """Thực thi cào dòng tiền ngoại realtime và room ngoại cho danh sách mã."""
        symbol_list = symbols or self.get_all_market_symbols()
        logger.info(f"Bắt đầu cào Khối ngoại realtime & Room ngoại cho {len(symbol_list)} mã vào CSDL {self.db_path}...")

        success_cnt = 0
        for i, sym in enumerate(symbol_list, start=1):
            logger.info(f"[{i}/{len(symbol_list)}] Đang xử lý mã: {sym}...")
            rec = self.fetch_symbol_foreign(sym)
            if rec and self.save_and_promote(rec):
                success_cnt += 1
                logger.info(f" -> [{sym}] Thành công: Mua={rec['foreign_buy_volume']:,}, Bán={rec['foreign_sell_volume']:,}, Room={rec['foreign_ownership_pct']}%.")
            else:
                logger.warning(f" -> [{sym}] Thất bại hoặc không có dữ liệu.")
            time.sleep(delay_sec)

        logger.info(f"Hoàn tất: {success_cnt}/{len(symbol_list)} mã thành công.")
        return {
            "total_symbols": len(symbol_list),
            "success_symbols": success_cnt,
        }


def main():
    parser = argparse.ArgumentParser(description="VESTA Intraday Foreign Flow & Ownership Room Crawler")
    parser.add_argument("--db-path", type=str, default="db/vesta.duckdb", help="Đường dẫn file DuckDB")
    parser.add_argument("--symbols", type=str, default="", help="Danh sách mã cổ phiếu")
    parser.add_argument("--all-symbols", action="store_true", help="Cào cho toàn bộ các mã cổ phiếu trên thị trường")
    parser.add_argument("--delay", type=float, default=0.4, help="Độ trễ giữa các mã (giây)")
    args = parser.parse_args()

    crawler = ForeignFlowIntradayCrawler(db_path=args.db_path)
    if args.all_symbols or not args.symbols:
        symbol_list = crawler.get_all_market_symbols() if args.all_symbols else ["SSI", "VND", "VCI", "HCM", "SHS", "HPG", "FPT", "VCB", "MWG"]
    else:
        symbol_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    res = crawler.run(symbol_list, delay_sec=args.delay)
    print("\n[CRAWL RESULT SUMMARY]")
    for k, v in res.items():
        print(f" - {k}: {v}")


if __name__ == "__main__":
    main()
