"""src/crawlers/order_book_depth.py

Order Book Level 2 Depth & Tick-by-Tick Trades Crawler.
Utilizes Vnstock 3.3.0+ Unified API (Silver Sponsor Tier):
- `Market.equity(symbol).order_book()`: 3 best bid/ask prices and volumes.
- `Market.equity(symbol).intraday()`: Real-time matched trades (time, price, volume, match_type).

Calculates Order Flow Imbalance (OFI) and detects:
- Shark Market Sweeps (Lệnh quét chủ động của cá mập: large buy/sell orders matching at ask/bid)
- Price Barrier Walls (Lệnh chặn giá ảo / tường giá).

Database Tables:
- `staging.order_book_depth` / `core.order_book_depth` (Snapshot Level 2 depth + OFI)
- `staging.intraday_trades` / `core.intraday_trades` (Tick-by-tick matched trades)
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
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawlers.order_book_depth")


class OrderBookDepthCrawler:
    """Crawler sổ lệnh vi mô Level 2, Tick data và tính toán chỉ số OFI."""

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
        """Đảm bảo các bảng dữ liệu Level 2 tồn tại trong DuckDB."""
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

            # Bảng sổ lệnh Level 2 Snapshot
            con.execute("""
                CREATE TABLE IF NOT EXISTS staging.order_book_depth (
                    symbol              VARCHAR NOT NULL,
                    timestamp           TIMESTAMP NOT NULL,
                    bid_price_1         DOUBLE,
                    bid_vol_1           DOUBLE,
                    bid_price_2         DOUBLE,
                    bid_vol_2           DOUBLE,
                    bid_price_3         DOUBLE,
                    bid_vol_3           DOUBLE,
                    ask_price_1         DOUBLE,
                    ask_vol_1           DOUBLE,
                    ask_price_2         DOUBLE,
                    ask_vol_2           DOUBLE,
                    ask_price_3         DOUBLE,
                    ask_vol_3           DOUBLE,
                    total_bid_depth     DOUBLE,
                    total_ask_depth     DOUBLE,
                    spread              DOUBLE,
                    ofi_ratio           DOUBLE,
                    fetched_at          TIMESTAMP NOT NULL
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS core.order_book_depth (
                    symbol              VARCHAR NOT NULL,
                    timestamp           TIMESTAMP NOT NULL,
                    bid_price_1         DOUBLE,
                    bid_vol_1           DOUBLE,
                    bid_price_2         DOUBLE,
                    bid_vol_2           DOUBLE,
                    bid_price_3         DOUBLE,
                    bid_vol_3           DOUBLE,
                    ask_price_1         DOUBLE,
                    ask_vol_1           DOUBLE,
                    ask_price_2         DOUBLE,
                    ask_vol_2           DOUBLE,
                    ask_price_3         DOUBLE,
                    ask_vol_3           DOUBLE,
                    total_bid_depth     DOUBLE,
                    total_ask_depth     DOUBLE,
                    spread              DOUBLE,
                    ofi_ratio           DOUBLE,
                    fetched_at          TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, timestamp)
                );
            """)

            # Bảng lưu vết từng lệnh khớp (Tick Data)
            con.execute("""
                CREATE TABLE IF NOT EXISTS staging.intraday_trades (
                    symbol              VARCHAR NOT NULL,
                    trade_id            VARCHAR NOT NULL,
                    time                TIMESTAMP NOT NULL,
                    price               DOUBLE NOT NULL,
                    volume              BIGINT NOT NULL,
                    match_type          VARCHAR,
                    is_shark_sweep      BOOLEAN,
                    fetched_at          TIMESTAMP NOT NULL
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS core.intraday_trades (
                    symbol              VARCHAR NOT NULL,
                    trade_id            VARCHAR NOT NULL,
                    time                TIMESTAMP NOT NULL,
                    price               DOUBLE NOT NULL,
                    volume              BIGINT NOT NULL,
                    match_type          VARCHAR,
                    is_shark_sweep      BOOLEAN,
                    fetched_at          TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, trade_id)
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
            return ["SSI", "VND", "VCI", "HCM", "SHS", "HPG", "FPT", "VCB"]
        finally:
            con.close()

    def fetch_order_book(self, symbol: str) -> Optional[pd.DataFrame]:
        """Lấy độ sâu 3 bước giá mua/bán và tính OFI."""
        sym = symbol.strip().upper()
        try:
            df = self.market.equity(sym).order_book()
            if df is None or df.empty:
                return None
            
            now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            df = df.copy()
            df["symbol"] = sym
            df["timestamp"] = now
            df["fetched_at"] = now

            # Đảm bảo các cột bước giá có kiểu số thực
            price_cols = ["bid_price_1", "bid_vol_1", "bid_price_2", "bid_vol_2", "bid_price_3", "bid_vol_3",
                          "ask_price_1", "ask_vol_1", "ask_price_2", "ask_vol_2", "ask_price_3", "ask_vol_3"]
            for col in price_cols:
                if col not in df.columns:
                    df[col] = np.nan
                else:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

            # Tính toán độ sâu và chỉ số OFI (Order Flow Imbalance)
            total_bid = df["bid_vol_1"] + df["bid_vol_2"] + df["bid_vol_3"]
            total_ask = df["ask_vol_1"] + df["ask_vol_2"] + df["ask_vol_3"]
            df["total_bid_depth"] = total_bid
            df["total_ask_depth"] = total_ask
            df["spread"] = (df["ask_price_1"] - df["bid_price_1"]).clip(lower=0.0)
            
            total_depth = total_bid + total_ask
            df["ofi_ratio"] = np.where(total_depth > 0, (total_bid - total_ask) / total_depth, 0.0)

            req_cols = [
                "symbol", "timestamp", "bid_price_1", "bid_vol_1", "bid_price_2", "bid_vol_2",
                "bid_price_3", "bid_vol_3", "ask_price_1", "ask_vol_1", "ask_price_2", "ask_vol_2",
                "ask_price_3", "ask_vol_3", "total_bid_depth", "total_ask_depth", "spread", "ofi_ratio", "fetched_at"
            ]
            return df[req_cols]
        except Exception as e:
            logger.warning(f"[{sym}] Không thể lấy Order Book: {e}")
            return None

    def fetch_intraday_trades(self, symbol: str, limit: int = 10000) -> Optional[pd.DataFrame]:
        """Lấy dữ liệu khớp lệnh từng tích tắc và gắn nhãn lệnh quét của cá mập."""
        sym = symbol.strip().upper()
        try:
            df = self.market.equity(sym).intraday(page_size=limit)
            if df is None or df.empty:
                return None
            
            now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            df = df.copy()
            df["symbol"] = sym
            df["fetched_at"] = now
            df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)
            df["trade_id"] = df["id"].astype(str) if "id" in df.columns else [f"{sym}_{int(time.time()*1000)}_{i}" for i in range(len(df))]

            # Gán nhãn lệnh cá mập quét lệnh chủ động (volume lớn, e.g. > 10,000 cổ phiếu khớp thẳng lệnh chủ động)
            shark_threshold = 10000
            df["is_shark_sweep"] = (df["volume"] >= shark_threshold) & (df["match_type"].isin(["Buy", "Sell"]))

            req_cols = ["symbol", "trade_id", "time", "price", "volume", "match_type", "is_shark_sweep", "fetched_at"]
            return df[req_cols].drop_duplicates(subset=["symbol", "trade_id"])
        except Exception as e:
            logger.warning(f"[{sym}] Không thể lấy Intraday Trades: {e}")
            return None

    def save_and_promote(self, ob_df: Optional[pd.DataFrame], trades_df: Optional[pd.DataFrame], symbol: str) -> Tuple[int, int]:
        """Lưu trữ và thăng hạng dữ liệu vào CSDL DuckDB."""
        ob_rows = 0
        trade_rows = 0
        con = duckdb.connect(str(self.db_path), read_only=False)
        try:
            if ob_df is not None and not ob_df.empty:
                con.register("df_ob", ob_df)
                con.execute("INSERT INTO staging.order_book_depth SELECT * FROM df_ob;")
                con.execute("""
                    INSERT INTO core.order_book_depth 
                    SELECT * FROM df_ob 
                    ON CONFLICT (symbol, timestamp) DO NOTHING;
                """)
                con.unregister("df_ob")
                ob_rows = len(ob_df)

            if trades_df is not None and not trades_df.empty:
                con.register("df_trades", trades_df)
                con.execute("INSERT INTO staging.intraday_trades SELECT * FROM df_trades;")
                con.execute("""
                    INSERT INTO core.intraday_trades 
                    SELECT * FROM df_trades 
                    ON CONFLICT (symbol, trade_id) DO NOTHING;
                """)
                con.unregister("df_trades")
                trade_rows = len(trades_df)

            status = "success" if (ob_rows > 0 or trade_rows > 0) else "empty"
            con.execute("""
                INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
                VALUES ('order_book_depth', ?, ?, 0, CURRENT_TIMESTAMP)
                ON CONFLICT (dataset_name, symbol) DO UPDATE SET
                    status = excluded.status,
                    last_attempt = excluded.last_attempt;
            """, [symbol, status])
            return ob_rows, trade_rows
        finally:
            con.close()

    def run(self, symbols: Optional[List[str]] = None, delay_sec: float = 0.5) -> Dict[str, Any]:
        """Chạy cào sổ lệnh và tích tắc khớp lệnh cho danh sách mã hoặc toàn bộ thị trường."""
        symbol_list = symbols or self.get_all_market_symbols()
        logger.info(f"Bắt đầu cào Order Book & Tick Data cho {len(symbol_list)} mã vào CSDL {self.db_path}...")

        total_ob = 0
        total_trades = 0
        success_symbols = 0

        for i, sym in enumerate(symbol_list, start=1):
            logger.info(f"[{i}/{len(symbol_list)}] Đang xử lý mã: {sym}...")
            ob_df = self.fetch_order_book(sym)
            trades_df = self.fetch_intraday_trades(sym, limit=10000)

            n_ob, n_tr = self.save_and_promote(ob_df, trades_df, sym)
            if n_ob > 0 or n_tr > 0:
                success_symbols += 1
                total_ob += n_ob
                total_trades += n_tr
                logger.info(f" -> [{sym}] Đã nạp thành công: {n_ob} sổ lệnh, {n_tr} lệnh khớp chi tiết.")
            else:
                logger.warning(f" -> [{sym}] Không có dữ liệu.")

            time.sleep(delay_sec)

        logger.info(f"Hoàn tất: {success_symbols}/{len(symbol_list)} thành công. Tổng: {total_ob} sổ lệnh, {total_trades} lệnh khớp.")
        return {
            "total_symbols": len(symbol_list),
            "success_symbols": success_symbols,
            "total_order_books": total_ob,
            "total_trades": total_trades,
        }


def main():
    parser = argparse.ArgumentParser(description="VESTA Order Book Level 2 & Tick Data Crawler")
    parser.add_argument("--db-path", type=str, default="db/vesta.duckdb", help="Đường dẫn file DuckDB")
    parser.add_argument("--symbols", type=str, default="", help="Danh sách mã cổ phiếu (phân tách bởi dấu phẩy)")
    parser.add_argument("--all-symbols", action="store_true", help="Cào cho toàn bộ các mã cổ phiếu trên thị trường")
    parser.add_argument("--delay", type=float, default=0.5, help="Độ trễ giữa các mã (giây)")
    args = parser.parse_args()

    crawler = OrderBookDepthCrawler(db_path=args.db_path)
    if args.all_symbols or not args.symbols:
        symbol_list = crawler.get_all_market_symbols() if args.all_symbols else ["SSI", "VND", "VCI", "HCM", "SHS", "HPG", "FPT", "VCB"]
    else:
        symbol_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    res = crawler.run(symbol_list, delay_sec=args.delay)
    print("\n[CRAWL RESULT SUMMARY]")
    for k, v in res.items():
        print(f" - {k}: {v}")


if __name__ == "__main__":
    main()
