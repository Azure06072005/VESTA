"""src/crawlers/macro_rates.py

Crawler & Ingester for Macroeconomic Benchmark Interest Rates & Government Bond Yields.
Captures:
1. Interbank Interest Rates (Lãi suất bình quân liên ngân hàng: ON, 1W, 2W, 1M, 3M)
2. Vietnam Government Bond Yields (Lợi suất Trái phiếu Chính phủ: VN10Y, VN5Y)

Sources:
- Investing.com (Historical daily series for VN10Y)
- Macro Policy & News corpus (Point-in-Time extracted interbank benchmark fixings)

Destination:
- staging.macro_rates (Raw intake)
- core.macro_rates (Promoted & deduplicated on rate_type + term + date)
- meta.crawl_progress (Job execution status tracking)
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict

from bs4 import BeautifulSoup
import duckdb
import pandas as pd
import requests

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crawlers.macro_rates")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
}


class MacroRatesCrawler:
    """Crawler & Ingester cho Lợi suất Trái phiếu Chính phủ & Lãi suất Liên ngân hàng."""

    def __init__(self, db_path: str | Path = "db/vesta.duckdb") -> None:
        self.db_path = Path(db_path)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._init_tables()

    def _init_tables(self) -> None:
        """Khởi tạo bảng staging, core và meta trong DuckDB."""
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
                CREATE TABLE IF NOT EXISTS staging.macro_rates (
                    rate_type     VARCHAR NOT NULL,
                    term          VARCHAR NOT NULL,
                    date          DATE NOT NULL,
                    rate_value    DOUBLE NOT NULL,
                    source        VARCHAR NOT NULL,
                    fetched_at    TIMESTAMP NOT NULL
                );
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS core.macro_rates (
                    rate_type     VARCHAR NOT NULL,
                    term          VARCHAR NOT NULL,
                    date          DATE NOT NULL,
                    rate_value    DOUBLE NOT NULL,
                    source        VARCHAR NOT NULL,
                    fetched_at    TIMESTAMP NOT NULL,
                    PRIMARY KEY (rate_type, term, date)
                );
            """)
        finally:
            con.close()

    def fetch_vn10y_investing(self) -> pd.DataFrame:
        """Cào chuỗi lịch sử lợi suất Trái phiếu Chính phủ 10 năm VN10Y từ Investing.com."""
        url = "https://www.investing.com/rates-bonds/vietnam-10-year-bond-yield-historical-data"
        logger.info(f"Đang cào dữ liệu VN10Y từ Investing.com: {url}...")

        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"Investing.com trả về status code {resp.status_code}")
                return pd.DataFrame()

            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            if not tables:
                logger.warning("Không tìm thấy bảng dữ liệu trên trang Investing.com")
                return pd.DataFrame()

            # Bảng đầu tiên chứa lịch sử theo phiên
            table = tables[0]
            rows = table.find_all("tr")
            records = []

            for tr in rows[1:]:
                tds = [td.text.strip() for td in tr.find_all("td")]
                if len(tds) >= 2:
                    date_str = tds[0]
                    price_str = tds[1].replace(",", "")
                    try:
                        # Parsing "Sep 17, 2026" or "%b %d, %Y"
                        dt_val = pd.to_datetime(date_str).date()
                        val = float(price_str)
                        records.append({
                            "rate_type": "GOV_BOND_YIELD",
                            "term": "10Y",
                            "date": dt_val,
                            "rate_value": val,
                            "source": "investing_vn10y",
                            "fetched_at": pd.Timestamp.now(),
                        })
                    except Exception:
                        continue

            df = pd.DataFrame(records)
            logger.info(f" -> Đã trích xuất thành công {len(df)} phiên VN10Y.")
            return df

        except Exception as e:
            logger.error(f"Lỗi khi cào VN10Y từ Investing.com: {e}")
            return pd.DataFrame()

    def backfill_interbank_from_corpus(self, limit: int = 500) -> pd.DataFrame:
        """Trích xuất dữ liệu lãi suất liên ngân hàng có cấu trúc từ core.macro_policy."""
        logger.info("Đang quét dữ liệu Lãi suất liên ngân hàng từ CSDL vĩ mô...")
        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            query = """
                SELECT published_at, headline, body 
                FROM core.macro_policy 
                WHERE regexp_matches(lower(headline), 'lãi suất.*(liên ngân hàng|qua đêm|1 tuần|1 tháng)')
                   OR regexp_matches(lower(body), 'lãi suất bình quân liên ngân hàng')
                ORDER BY published_at DESC 
                LIMIT ?;
            """
            raw_df = con.execute(query, [limit]).df()
        finally:
            con.close()

        records = []
        # Regex trích xuất lãi suất qua đêm: qua đêm [là|đạt|ở mức]?\s*(\d+[.,]\d+)\s*%/năm
        pat_on = re.compile(r"qua\s+đêm(?:\s+(?:là|ở\s+mức|đạt|tăng\s+lên|giảm\s+xuống))?\s*[:\s]*(\d+[.,]\d+)\s*%", re.IGNORECASE)
        pat_1w = re.compile(r"1\s+tuần(?:\s+(?:là|ở\s+mức|đạt|tăng\s+lên|giảm\s+xuống))?\s*[:\s]*(\d+[.,]\d+)\s*%", re.IGNORECASE)
        pat_1m = re.compile(r"1\s+tháng(?:\s+(?:là|ở\s+mức|đạt|tăng\s+lên|giảm\s+xuống))?\s*[:\s]*(\d+[.,]\d+)\s*%", re.IGNORECASE)

        for _, row in raw_df.iterrows():
            if pd.isnull(row["published_at"]):
                continue
            date_val = pd.to_datetime(row["published_at"]).date()
            text = (str(row["headline"]) + " " + str(row.get("body") or ""))[:2000]

            m_on = pat_on.search(text)
            if m_on:
                val = float(m_on.group(1).replace(",", "."))
                if 0.1 <= val <= 25.0:  # Bound check hợp lý
                    records.append({
                        "rate_type": "INTERBANK",
                        "term": "ON",
                        "date": date_val,
                        "rate_value": val,
                        "source": "sbv_corpus_fix",
                        "fetched_at": pd.Timestamp.now(),
                    })

            m_1w = pat_1w.search(text)
            if m_1w:
                val = float(m_1w.group(1).replace(",", "."))
                if 0.1 <= val <= 25.0:
                    records.append({
                        "rate_type": "INTERBANK",
                        "term": "1W",
                        "date": date_val,
                        "rate_value": val,
                        "source": "sbv_corpus_fix",
                        "fetched_at": pd.Timestamp.now(),
                    })

            m_1m = pat_1m.search(text)
            if m_1m:
                val = float(m_1m.group(1).replace(",", "."))
                if 0.1 <= val <= 25.0:
                    records.append({
                        "rate_type": "INTERBANK",
                        "term": "1M",
                        "date": date_val,
                        "rate_value": val,
                        "source": "sbv_corpus_fix",
                        "fetched_at": pd.Timestamp.now(),
                    })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.drop_duplicates(subset=["rate_type", "term", "date"])
        logger.info(f" -> Trích xuất thành công {len(df)} mốc dữ liệu Lãi suất liên ngân hàng từ corpus.")
        return df

    def save_and_promote(self, df: pd.DataFrame, dataset_key: str) -> int:
        """Lưu trữ dữ liệu vào staging và upsert sang core."""
        if df is None or df.empty:
            return 0

        con = duckdb.connect(str(self.db_path), read_only=False)
        try:
            con.register("df_rates_staging", df)
            con.execute("INSERT INTO staging.macro_rates SELECT * FROM df_rates_staging;")

            con.execute("""
                INSERT INTO core.macro_rates
                SELECT rate_type, term, date, rate_value, source, fetched_at
                FROM df_rates_staging
                ON CONFLICT (rate_type, term, date) DO UPDATE SET
                    rate_value = EXCLUDED.rate_value,
                    source = EXCLUDED.source,
                    fetched_at = EXCLUDED.fetched_at;
            """)

            now_ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute(f"""
                INSERT INTO meta.crawl_progress (dataset_name, symbol, status, retry_count, last_attempt)
                VALUES ('macro_rates', '{dataset_key}', 'success', 0, '{now_ts}')
                ON CONFLICT (dataset_name, symbol) DO UPDATE SET
                    status = 'success',
                    last_attempt = '{now_ts}';
            """)
            return len(df)
        finally:
            con.close()

    def run(self) -> Dict[str, Any]:
        """Chạy toàn bộ tiến trình cào Lợi suất TPCP và Lãi suất liên ngân hàng."""
        total_rows = 0

        # 1. Cào VN10Y từ Investing
        df_vn10y = self.fetch_vn10y_investing()
        if not df_vn10y.empty:
            rows = self.save_and_promote(df_vn10y, "VN10Y")
            total_rows += rows

        # 2. Backfill Lãi suất liên ngân hàng từ corpus
        df_ib = self.backfill_interbank_from_corpus(limit=1000)
        if not df_ib.empty:
            rows = self.save_and_promote(df_ib, "INTERBANK")
            total_rows += rows

        return {
            "vn10y_rows": len(df_vn10y),
            "interbank_rows": len(df_ib),
            "total_promoted": total_rows,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="VESTA Macro Rates Crawler (VN10Y & Interbank)")
    parser.add_argument("--db-path", type=str, default="db/vesta.duckdb", help="Path to DuckDB database")
    args = parser.parse_args()

    crawler = MacroRatesCrawler(db_path=args.db_path)
    res = crawler.run()
    print("\n[MACRO RATES CRAWL RESULT SUMMARY]")
    for k, v in res.items():
        print(f" - {k}: {v}")


if __name__ == "__main__":
    main()
