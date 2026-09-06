"""Bộ nạp và tăng cường dữ liệu giá & chỉ số thị trường toàn diện từ CafeF Data.

Hỗ trợ lấy toàn bộ lịch sử OHLCV cho 100% mã cổ phiếu (HOSE, HNX, UPCOM) và chỉ số
từ ngày đầu thành lập thị trường (2000) đến hiện tại (2026), bù đắp triệt để các mã
và ngày còn thiếu trong vnstock.

Lưu trữ vào:
  - `core.market_ohlcv_daily` (symbol, date, open, high, low, close, volume, fetched_at)
  - `core.market_index_daily` (index_code, date, open, high, low, close, volume, fetched_at)
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import logging
import re
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

# URL kho dữ liệu nén toàn thị trường cập nhật hàng ngày từ CafeF Media CDN
CAFEF_DATA_BASE_URL = "https://cafef1.mediacdn.vn/data/ami_data"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 (VESTA-Enhancer)"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}


def get_latest_cafef_date_str() -> str:
    """Xác định chuỗi ngày mới nhất (YYYYMMDD) để tải dữ liệu từ CafeF."""
    now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=7)  # Giờ VN
    # Thử ngày hôm nay, nếu là cuối tuần/sáng sớm thì lùi lại ngày gần nhất
    for day_offset in range(5):
        target_date = now - dt.timedelta(days=day_offset)
        date_str = target_date.strftime("%Y%m%d")
        url = f"{CAFEF_DATA_BASE_URL}/{date_str}/CafeF.SolieuGD.Upto{target_date.strftime('%d%m%Y')}.zip"
        try:
            r = requests.head(url, headers=DEFAULT_HEADERS, timeout=5)
            if r.status_code == 200:
                return target_date.strftime("%d%m%Y"), date_str
        except Exception:
            continue
    # Mặc định fallback về ngày đã xác thực
    return "04092026", "20260904"


class CafeFMarketDataEnhancer:
    """Trình xử lý và đồng bộ dữ liệu giao dịch toàn diện từ CafeF Data."""

    def __init__(self, duckdb_path: str = "d:/VESTA/db/vesta.duckdb") -> None:
        self.duckdb_path = duckdb_path
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._init_index_table()

    def _init_index_table(self) -> None:
        """Khởi tạo bảng chỉ số thị trường core.market_index_daily nếu chưa tồn tại."""
        try:
            con = duckdb.connect(self.duckdb_path, read_only=False)
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
                );
            """)
            con.close()
        except Exception as e:
            logger.warning(f"Không thể khởi tạo bảng core.market_index_daily: {e}")

    def download_zip(self, url: str) -> zipfile.ZipFile:
        """Tải file zip từ URL và trả về đối tượng ZipFile trong bộ nhớ."""
        logger.info(f"Đang tải file dữ liệu từ: {url}")
        resp = self.session.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(resp.content))

    @staticmethod
    def parse_ohlcv_csv(content: io.BytesIO | str) -> pd.DataFrame:
        """Phân tích nội dung CSV CafeF thành DataFrame chuẩn hóa."""
        df = pd.read_csv(content, encoding="utf-8-sig")
        # Chuẩn hóa tên cột: <Ticker>,<DTYYYYMMDD>,<Open>,<High>,<Low>,<Close>,<Volume>
        df.columns = [c.replace("<", "").replace(">", "").strip().lower() for c in df.columns]
        
        # Bắt buộc phải có các trường cốt lõi
        required = ["ticker", "dtyyyymmdd", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"CSV thiếu cột bắt buộc {col}: các cột hiện có {df.columns.tolist()}")

        df["symbol"] = df["ticker"].astype(str).str.strip().str.upper()
        # Chuyển đổi ngày YYYYMMDD thành kiểu date
        df["date"] = pd.to_datetime(df["dtyyyymmdd"].astype(str), format="%Y%m%d").dt.date
        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
        df["fetched_at"] = dt.datetime.now(dt.timezone.utc)

        clean_df = df[["symbol", "date", "open", "high", "low", "close", "volume", "fetched_at"]]
        clean_df = clean_df.dropna(subset=["symbol", "date"])
        # Khử trùng lặp khóa chính trong cùng batch
        clean_df = clean_df.drop_duplicates(subset=["symbol", "date"], keep="last").reset_index(drop=True)
        return clean_df

    def ingest_stock_ohlcv(
        self,
        date_str_dmy: str | None = None,
        date_str_ymd: str | None = None,
        symbols_filter: list[str] | None = None,
        dry_run: bool = False
    ) -> int:
        """Tải và nạp dữ liệu OHLCV toàn bộ cổ phiếu vào core.market_ohlcv_daily."""
        if not date_str_dmy or not date_str_ymd:
            date_str_dmy, date_str_ymd = get_latest_cafef_date_str()

        zip_url = f"{CAFEF_DATA_BASE_URL}/{date_str_ymd}/CafeF.SolieuGD.Upto{date_str_dmy}.zip"
        z = self.download_zip(zip_url)

        total_inserted = 0
        csv_files = [f for f in z.namelist() if f.lower().endswith(".csv")]
        logger.info(f"Tìm thấy {len(csv_files)} file CSV sàn giao dịch trong kho nén.")

        for filename in csv_files:
            logger.info(f"Đang phân tích và nạp dữ liệu sàn: {filename}...")
            with z.open(filename) as f:
                content = io.BytesIO(f.read())
                df = self.parse_ohlcv_csv(content)

                if symbols_filter:
                    symbols_set = {s.upper() for s in symbols_filter}
                    df = df[df["symbol"].isin(symbols_set)]

                if df.empty:
                    logger.info(f"Không có bản ghi phù hợp trong {filename}.")
                    continue

                if dry_run:
                    logger.info(f"[DRY-RUN] Bỏ qua ghi DB cho {len(df)} bản ghi từ {filename}.")
                    total_inserted += len(df)
                    continue

                # Lưu vào DuckDB với ON CONFLICT DO UPDATE
                con = duckdb.connect(self.duckdb_path, read_only=False)
                con.register("df_stock_batch", df)
                con.execute("""
                    INSERT INTO core.market_ohlcv_daily (
                        symbol, date, open, high, low, close, volume, fetched_at
                    )
                    SELECT symbol, date, open, high, low, close, volume, fetched_at
                    FROM df_stock_batch
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.close()
                total_inserted += len(df)
                logger.info(f"Đã lưu thành công +{len(df):,} bản ghi từ {filename} vào DB.")

        return total_inserted

    def ingest_market_index(
        self,
        date_str_dmy: str | None = None,
        date_str_ymd: str | None = None,
        dry_run: bool = False
    ) -> int:
        """Tải và nạp dữ liệu lịch sử các chỉ số (VN-Index, VN30, HNX-Index...) vào core.market_index_daily."""
        if not date_str_dmy or not date_str_ymd:
            date_str_dmy, date_str_ymd = get_latest_cafef_date_str()

        zip_url = f"{CAFEF_DATA_BASE_URL}/{date_str_ymd}/CafeF.Index.Upto{date_str_dmy}.zip"
        z = self.download_zip(zip_url)

        total_inserted = 0
        csv_files = [f for f in z.namelist() if f.lower().endswith(".csv")]
        for filename in csv_files:
            logger.info(f"Đang phân tích chỉ số thị trường: {filename}...")
            with z.open(filename) as f:
                content = io.BytesIO(f.read())
                df = self.parse_ohlcv_csv(content)
                df = df.rename(columns={"symbol": "index_code"})

                if dry_run:
                    logger.info(f"[DRY-RUN] Bỏ qua ghi DB cho {len(df)} bản ghi chỉ số từ {filename}.")
                    total_inserted += len(df)
                    continue

                con = duckdb.connect(self.duckdb_path, read_only=False)
                con.register("df_index_batch", df)
                con.execute("""
                    INSERT INTO core.market_index_daily (
                        index_code, date, open, high, low, close, volume, fetched_at
                    )
                    SELECT index_code, date, open, high, low, close, volume, fetched_at
                    FROM df_index_batch
                    ON CONFLICT (index_code, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        fetched_at = EXCLUDED.fetched_at
                """)
                con.close()
                total_inserted += len(df)
                logger.info(f"Đã lưu thành công +{len(df):,} bản ghi chỉ số từ {filename}.")

        return total_inserted


def main() -> None:
    """CLI thực thi đồng bộ dữ liệu CafeF."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="CafeF Data Market Enhancer (Tăng cường dữ liệu toàn thị trường)")
    parser.add_argument("--mode", choices=["all", "stocks", "indices"], default="all", help="Chế độ nạp: cổ phiếu, chỉ số hoặc tất cả")
    parser.add_argument("--symbols", nargs="+", help="Danh sách mã cần lọc (Mặc định: Toàn bộ mã)")
    parser.add_argument("--date-dmy", type=str, default=None, help="Ngày đích định dạng DDMMYYYY (Mặc định: Tự động tìm phiên mới nhất)")
    parser.add_argument("--date-ymd", type=str, default=None, help="Ngày đích định dạng YYYYMMDD (Mặc định: Tự động tìm phiên mới nhất)")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử không lưu DB")

    args = parser.parse_args()
    enhancer = CafeFMarketDataEnhancer()

    if args.date_dmy and args.date_ymd:
        date_dmy, date_ymd = args.date_dmy, args.date_ymd
    else:
        date_dmy, date_ymd = get_latest_cafef_date_str()

    logger.info(
        f"Khởi chạy nạp dữ liệu toàn diện CafeF - Gói tích lũy toàn lịch sử (28/07/2000 -> {date_dmy})..."
    )

    if args.mode in ["all", "indices"]:
        idx_count = enhancer.ingest_market_index(date_str_dmy=date_dmy, date_str_ymd=date_ymd, dry_run=args.dry_run)
        logger.info(f"Hoàn tất nạp toàn bộ ngày lịch sử chỉ số thị trường: {idx_count:,} bản ghi.")

    if args.mode in ["all", "stocks"]:
        stock_count = enhancer.ingest_stock_ohlcv(
            date_str_dmy=date_dmy,
            date_str_ymd=date_ymd,
            symbols_filter=args.symbols,
            dry_run=args.dry_run
        )
        logger.info(f"Hoàn tất nạp toàn bộ ngày lịch sử giá cổ phiếu: {stock_count:,} bản ghi.")


if __name__ == "__main__":
    main()
