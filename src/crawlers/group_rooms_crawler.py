"""Module cào và đồng bộ toàn diện 23 rổ nhóm và chỉ số ngành từ VNDIRECT DChart API
vào core.market_index_daily trong db/vesta_ohlcv.duckdb.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
import time
from pathlib import Path
import duckdb
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("group_rooms_crawler")

PROJECT_DIR = "d:/VESTA"
OHLCV_DB = f"{PROJECT_DIR}/db/admin/vesta_ohlcv.duckdb"

# Danh sách đầy đủ 23 chỉ số nhóm / rổ phòng / ngành từ HOSE
GROUP_ROOMS_MAP = {
    # 1. Nhóm quy mô vốn hóa & thị trường chung
    'VN30': 'VN30 (Top 30 Large Cap)',
    'VN100': 'VN100 (Top 100 Large & Mid Cap)',
    'VNMID': 'VNMidCap (70 doanh nghiệp vốn hóa vừa)',
    'VNSML': 'VNSmallCap (Doanh nghiệp vốn hóa nhỏ)',
    'VNALL': 'VNAllShare (Toàn bộ cổ phiếu chuẩn sàn HOSE)',
    'VNX50': 'VNX50 (Top 50 liên sàn HOSE & HNX)',
    'VNXALL': 'VNX AllShare (Toàn thị trường liên sàn)',
    
    # 2. Nhóm rổ room ngoại và đầu tư chiến lược
    'VNDIAMOND': 'VN-Diamond (Cổ phiếu kim cương kín room ngoại >= 95%)',
    'VNFINLEAD': 'VN-FinLead (Ngành tài chính dẫn dắt)',
    'VNFINSELECT': 'VN-FinSelect (Ngành tài chính tuyển chọn)',
    'VNSI': 'VN-Sustainability Index (Phát triển bền vững ESG)',
    'VNDIVIDEND': 'VN-High Dividend (Cổ tức cao)',
    'VNMITECH': 'VN-MiTech (Công nghệ & Viễn thông)',
    
    # 3. 10 Nhóm ngành phân loại chuẩn ICB
    'VNFIN': 'VN-Financials (Ngân hàng, Chứng khoán, Bảo hiểm)',
    'VNREAL': 'VN-Real Estate (Bất động sản)',
    'VNMAT': 'VN-Materials (Thép, Hóa chất, Vật liệu xây dựng)',
    'VNIND': 'VN-Industrials (Công nghiệp, Vận tải, Cảng biển)',
    'VNCONS': 'VN-Consumer Staples (Hàng tiêu dùng thiết yếu)',
    'VNCOND': 'VN-Consumer Discretionary (Hàng tiêu dùng không thiết yếu)',
    'VNHEAL': 'VN-Health Care (Dược phẩm, Y tế)',
    'VNENE': 'VN-Energy (Năng lượng, Dầu khí, Khai khoáng)',
    'VNUTI': 'VN-Utilities (Tiện ích Điện, Nước, Khí đốt)',
    'VNIT': 'VN-Information Technology (Công nghệ Thông tin)'
}

VND_DCHART_BASE = "https://dchart-api.vndirect.com.vn/dchart/history"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


class GroupRoomsCrawler:
    """Crawler lấy trọn bộ dữ liệu lịch sử cho các rổ chỉ số nhóm và ngành."""

    def __init__(self, duckdb_path: str = OHLCV_DB) -> None:
        self.duckdb_path = duckdb_path

    def fetch_index_bars(self, symbol: str, from_year: int = 2015) -> pd.DataFrame:
        """Tải lịch sử nến ngày từ VNDIRECT DChart API."""
        now_ts = int(time.time())
        from_ts = int(time.mktime(time.strptime(f"{from_year}-01-01", "%Y-%m-%d")))
        url = f"{VND_DCHART_BASE}?resolution=D&symbol={symbol}&from={from_ts}&to={now_ts}"

        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                logger.warning(f"Lỗi HTTP {r.status_code} khi tải {symbol}")
                return pd.DataFrame()

            data = r.json()
            if data.get("s") != "ok" or not data.get("t"):
                logger.warning(f"Dữ liệu rỗng cho {symbol}")
                return pd.DataFrame()

            timestamps = data["t"]
            opens = data.get("o", [None] * len(timestamps))
            highs = data.get("h", [None] * len(timestamps))
            lows = data.get("l", [None] * len(timestamps))
            closes = data.get("c", [None] * len(timestamps))
            volumes = data.get("v", [0] * len(timestamps))

            dates = [dt.datetime.fromtimestamp(ts).date() for ts in timestamps]
            now = dt.datetime.now()

            s_open = pd.Series(pd.to_numeric(opens, errors="coerce"))
            s_high = pd.Series(pd.to_numeric(highs, errors="coerce"))
            s_low = pd.Series(pd.to_numeric(lows, errors="coerce"))
            s_close = pd.Series(pd.to_numeric(closes, errors="coerce"))
            s_vol = pd.Series(pd.to_numeric(volumes, errors="coerce")).fillna(0).astype("int64")

            df = pd.DataFrame({
                "index_code": symbol,
                "date": dates,
                "open": s_open,
                "high": s_high,
                "low": s_low,
                "close": s_close,
                "volume": s_vol,
                "fetched_at": now
            })
            return df
        except Exception as e:
            logger.error(f"Lỗi khi cào dữ liệu {symbol}: {e}")
            return pd.DataFrame()

    def save_to_duckdb(self, df: pd.DataFrame) -> int:
        """Ghi dữ liệu vào core.market_index_daily với UPSERT an toàn."""
        if df.empty:
            return 0

        con = duckdb.connect(self.duckdb_path, read_only=False)
        try:
            # Đảm bảo có Unique Index trên (index_code, date)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_market_index_daily_key 
                ON core.market_index_daily (index_code, date);
            """)

            con.register("df_incoming", df)
            con.execute("""
                INSERT INTO core.market_index_daily (
                    index_code, date, open, high, low, close, volume, fetched_at
                )
                SELECT index_code, date, open, high, low, close, volume, fetched_at
                FROM df_incoming
                ON CONFLICT (index_code, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    fetched_at = EXCLUDED.fetched_at;
            """)
            return len(df)
        finally:
            con.close()

    def crawl_all(self) -> dict[str, int]:
        """Cào và lưu toàn bộ 23 rổ nhóm chỉ số."""
        results = {}
        for sym, name in GROUP_ROOMS_MAP.items():
            t0 = time.time()
            df = self.fetch_index_bars(sym)
            if not df.empty:
                count = self.save_to_duckdb(df)
                elapsed = time.time() - t0
                logger.info(f"✅ {sym:12} ({name[:32]}...): Lưu +{count:,} phiên [{elapsed:.2f}s]")
                results[sym] = count
            else:
                logger.warning(f"⚠️ {sym:12}: Không có dữ liệu")
                results[sym] = 0
            time.sleep(0.1)  # Tránh nghẽn mạng
        return results


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logger.info("=== BẮT ĐẦU CÀO BÙ TOÀN BỘ 23 RỔ NHÓM VÀ NGÀNH (GROUP ROOMS) ===")
    crawler = GroupRoomsCrawler()
    results = crawler.crawl_all()

    total_ingested = sum(results.values())
    logger.info(f"\n🎉 HOÀN TẤT ĐỒNG BỘ 23 RỔ NHÓM: Tổng cộng nạp +{total_ingested:,} phiên lịch sử!")


if __name__ == "__main__":
    main()
