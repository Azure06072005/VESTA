"""CafeF Foreign Flow & Ownership Ingester (cafef_foreign_flow.py).

Thu thập và nạp dữ liệu giao dịch của nhà đầu tư nước ngoài (Khối ngoại) từ CafeF Data:
- Khối lượng mua / bán, Giá trị mua / bán của khối ngoại.
- Mua ròng (Net Buy Volume/Value).
- Tỷ lệ sở hữu và Room nước ngoài (Foreign Room).

Lưu trữ vào:
- `core.market_foreign_flow_daily` (primary key: `symbol, date`)
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import db

logger = logging.getLogger(__name__)

CAFEF_DATA_BASE_URL = "https://cafef1.mediacdn.vn/data/ami_data"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Foreign-Flow)"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}


class CafeFForeignFlowIngester:
    """Trình xử lý dữ liệu giao dịch khối ngoại từ CafeF."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb") -> None:
        self.duckdb_path = duckdb_path
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._init_table()

    def _init_table(self) -> None:
        """Khởi tạo bảng core.market_foreign_flow_daily trong DuckDB."""
        try:
            con = duckdb.connect(self.duckdb_path, read_only=False)
            con.execute("CREATE SCHEMA IF NOT EXISTS core;")
            con.execute("""
                CREATE TABLE IF NOT EXISTS core.market_foreign_flow_daily (
                    symbol VARCHAR NOT NULL,
                    date DATE NOT NULL,
                    buy_volume DOUBLE,
                    sell_volume DOUBLE,
                    buy_value DOUBLE,
                    sell_value DOUBLE,
                    net_volume DOUBLE,
                    net_value DOUBLE,
                    foreign_room DOUBLE,
                    fetched_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (symbol, date)
                );
            """)
            con.close()
        except Exception as e:
            logger.warning(f"Lỗi khi khởi tạo bảng core.market_foreign_flow_daily: {e}")

    @staticmethod
    def parse_nn_csv(content: io.BytesIO | str) -> pd.DataFrame:
        """Phân tích file CSV giao dịch khối ngoại CafeF (NN_HSX, NN_HNX, NN_UPCOM)."""
        df = pd.read_csv(content, encoding="utf-8-sig")
        df.columns = [c.replace("<", "").replace(">", "").strip().lower() for c in df.columns]

        required = ["ticker", "dtyyyymmdd", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"CSV thiếu cột bắt buộc {col}")

        df["symbol"] = df["ticker"].astype(str).str.strip().str.upper()
        df["date"] = pd.to_datetime(df["dtyyyymmdd"].astype(str), format="%Y%m%d").dt.date

        # Cột open/high/low/close trong file NN đại diện cho các trường giao dịch ngoại
        df["buy_volume"] = pd.to_numeric(df["open"], errors="coerce").fillna(0)
        df["sell_volume"] = pd.to_numeric(df["high"], errors="coerce").fillna(0)
        df["buy_value"] = pd.to_numeric(df["low"], errors="coerce").fillna(0)
        df["sell_value"] = pd.to_numeric(df["close"], errors="coerce").fillna(0)
        df["net_volume"] = df["buy_volume"] - df["sell_volume"]
        df["net_value"] = df["buy_value"] - df["sell_value"]
        df["foreign_room"] = pd.to_numeric(df.get("oi", 0), errors="coerce").fillna(0)
        df["fetched_at"] = dt.datetime.now(dt.timezone.utc)

        clean_df = df[[
            "symbol", "date", "buy_volume", "sell_volume",
            "buy_value", "sell_value", "net_volume", "net_value",
            "foreign_room", "fetched_at"
        ]].dropna(subset=["symbol", "date"]).drop_duplicates(subset=["symbol", "date"], keep="last").reset_index(drop=True)
        return clean_df

    def ingest_zip_stream(self, zip_url: str, symbols_filter: list[str] | None = None, dry_run: bool = False) -> int:
        """Tải file zip và nạp toàn bộ các file NN vào DuckDB."""
        logger.info(f"Đang tải file giao dịch khối ngoại: {zip_url}...")
        resp = self.session.get(zip_url, stream=True, timeout=120)
        resp.raise_for_status()

        total_inserted = 0
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            # Lọc các file giao dịch khối ngoại NN (NN_HSX, NN_HNX, NN_UPCOM)
            nn_files = [f for f in z.namelist() if "NN_" in f and f.lower().endswith(".csv")]
            logger.info(f"Tìm thấy {len(nn_files)} file dữ liệu khối ngoại trong kho nén.")

            for filename in nn_files:
                logger.info(f"Đang xử lý dữ liệu khối ngoại: {filename}...")
                with z.open(filename) as f:
                    df = self.parse_nn_csv(io.BytesIO(f.read()))

                    if symbols_filter:
                        symbols_set = {s.upper() for s in symbols_filter}
                        df = df[df["symbol"].isin(symbols_set)]

                    if df.empty:
                        continue

                    if dry_run:
                        logger.info(f"[DRY-RUN] Bỏ qua ghi DB cho {len(df)} bản ghi từ {filename}.")
                        total_inserted += len(df)
                        continue

                    # Ghi vào DuckDB kèm cơ chế retry
                    max_retries = 5
                    for attempt in range(max_retries):
                        try:
                            con = duckdb.connect(self.duckdb_path, read_only=False)
                            con.register("df_nn_batch", df)
                            con.execute("""
                                INSERT INTO core.market_foreign_flow_daily (
                                    symbol, date, buy_volume, sell_volume,
                                    buy_value, sell_value, net_volume, net_value,
                                    foreign_room, fetched_at
                                )
                                SELECT
                                    symbol, date, buy_volume, sell_volume,
                                    buy_value, sell_value, net_volume, net_value,
                                    foreign_room, fetched_at
                                FROM df_nn_batch
                                ON CONFLICT (symbol, date) DO UPDATE SET
                                    buy_volume = EXCLUDED.buy_volume,
                                    sell_volume = EXCLUDED.sell_volume,
                                    buy_value = EXCLUDED.buy_value,
                                    sell_value = EXCLUDED.sell_value,
                                    net_volume = EXCLUDED.net_volume,
                                    net_value = EXCLUDED.net_value,
                                    foreign_room = EXCLUDED.foreign_room,
                                    fetched_at = EXCLUDED.fetched_at
                            """)
                            con.close()
                            total_inserted += len(df)
                            logger.info(f"Đã lưu thành công +{len(df):,} bản ghi khối ngoại từ {filename}.")
                            break
                        except Exception as e:
                            import time
                            logger.warning(f"Thử {attempt+1}/{max_retries} nạp CCNN bị lock ({e}). Chờ 2s...")
                            time.sleep(2.0)

        return total_inserted


def main() -> None:
    """CLI thực thi nạp dữ liệu khối ngoại."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="CafeF Foreign Investor Flow Ingester")
    parser.add_argument("--daily-only", action="store_true", help="Chỉ nạp phiên giao dịch gần nhất (nhanh)")
    parser.add_argument("--symbols", nargs="+", help="Lọc mã cổ phiếu cần nạp")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không ghi DB")

    args = parser.parse_args()
    ingester = CafeFForeignFlowIngester()

    # Xác định URL tải (Upto hoặc Daily)
    if args.daily_only:
        zip_url = f"{CAFEF_DATA_BASE_URL}/20260904/CafeF.CCNN.04092026.zip"
    else:
        zip_url = f"{CAFEF_DATA_BASE_URL}/20260904/CafeF.CCNN.Upto04092026.zip"

    count = ingester.ingest_zip_stream(zip_url, symbols_filter=args.symbols, dry_run=args.dry_run)
    print(f"Tổng số bản ghi giao dịch khối ngoại đã nạp: {count:,}")


if __name__ == "__main__":
    main()
