"""
Yahoo Finance Global Expansion Crawler
1. Macro Commodities & Asian Indices from 2000 -> core.market_index_daily
   - Asian Indices: ^N225 (Nikkei), ^HSI (Hang Seng), 000001.SS (Shanghai), ^KS11 (KOSPI), ^TWII (Taiwan), ^STI (Singapore)
   - Commodities & Ag: KC=F (Coffee), ZR=F (Rice), TIO=F (Iron Ore), HRC=F (Steel), ZC=F (Corn), ZS=F (Soybean), ZW=F (Wheat), SB=F (Sugar), CT=F (Cotton)
2. Magnificent 7 Tech Leaders from 2000 -> core.market_global_equity_daily
   - Symbols: NVDA, AAPL, MSFT, GOOGL, AMZN, TSLA, META
"""

import datetime as dt
import logging
import sys
import time
from typing import Any
import duckdb
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yahoo_global_expansion")

DB_PATH = "d:/VESTA/db/vesta_latest_backup.duckdb"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

ASIAN_INDICES = [
    ("^N225", "Nikkei 225 (Japan)"),
    ("^HSI", "Hang Seng Index (Hong Kong)"),
    ("000001.SS", "Shanghai Composite (China)"),
    ("^KS11", "KOSPI Composite (South Korea)"),
    ("^TWII", "Taiwan Weighted Index (Taiwan)"),
    ("^STI", "Straits Times Index (Singapore)"),
]

COMMODITIES_AG = [
    ("KC=F", "Coffee 'C' Futures (Cà phê)"),
    ("ZR=F", "Rough Rice Futures (Gạo)"),
    ("TIO=F", "Iron Ore 62% Fe CFR China (Quặng sắt)"),
    ("HRC=F", "Steel HRC Futures (Thép cuộn)"),
    ("ZC=F", "Corn Futures (Ngô)"),
    ("ZS=F", "Soybean Futures (Đậu tương)"),
    ("ZW=F", "Wheat Futures (Lúa mì)"),
    ("SB=F", "Sugar #11 Futures (Đường)"),
    ("CT=F", "Cotton #2 Futures (Bông)"),
]

MAG7_SYMBOLS = [
    ("NVDA", "Nvidia Corporation"),
    ("AAPL", "Apple Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("GOOGL", "Alphabet Inc. (Google)"),
    ("AMZN", "Amazon.com Inc."),
    ("TSLA", "Tesla Inc."),
    ("META", "Meta Platforms Inc.")
]


def init_global_equity_tables(con: duckdb.DuckDBPyConnection):
    """Creates staging and core.market_global_equity_daily tables if not exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS staging.market_global_equity_daily (
            symbol      VARCHAR NOT NULL,
            date        DATE NOT NULL,
            open        DOUBLE,
            high        DOUBLE,
            low         DOUBLE,
            close       DOUBLE,
            volume      BIGINT,
            fetched_at  TIMESTAMP NOT NULL
        );
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS core.market_global_equity_daily (
            symbol      VARCHAR NOT NULL,
            date        DATE NOT NULL,
            open        DOUBLE,
            high        DOUBLE,
            low         DOUBLE,
            close       DOUBLE,
            volume      BIGINT,
            fetched_at  TIMESTAMP NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)


def fetch_symbol_bars(symbol: str, name: str, start_year: int = 2000) -> list[dict[str, Any]]:
    """Fetches daily historical OHLCV from start_year for a symbol."""
    p1 = int(dt.datetime(start_year, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.now(dt.timezone.utc).timestamp())
    now = dt.datetime.now(dt.timezone.utc)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d"

    bars = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Lỗi tải {symbol}: HTTP {resp.status_code}")
            return []
        data = resp.json()
        res = data.get("chart", {}).get("result", [])
        if not res:
            return []
        chart_res = res[0]
        timestamps = chart_res.get("timestamp", [])
        indicators = chart_res.get("indicators", {}).get("quote", [{}])[0]
        opens = indicators.get("open", [])
        highs = indicators.get("high", [])
        lows = indicators.get("low", [])
        closes = indicators.get("close", [])
        volumes = indicators.get("volume", [])

        for i, ts in enumerate(timestamps):
            c = closes[i] if i < len(closes) else None
            if c is None:
                continue
            o = opens[i] if i < len(opens) and opens[i] is not None else c
            h = highs[i] if i < len(highs) and highs[i] is not None else c
            l = lows[i] if i < len(lows) and lows[i] is not None else c
            v = int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0

            bar_date = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()
            bars.append({
                "code": symbol,
                "date": bar_date,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": v,
                "fetched_at": now
            })

        logger.info(f"-> {symbol:<10} ({name}): Đã cào {len(bars):,} phiên (từ {bars[0]['date']} đến {bars[-1]['date']}).")
        time.sleep(0.2)
    except Exception as e:
        logger.warning(f"Lỗi khi cào {symbol}: {e}")

    return bars


def run_global_expansion(start_year: int = 2000, db_path: str = DB_PATH):
    """Crawls and ingests both expanded macro assets and Mag7 stocks."""
    logger.info("=========================================================================")
    logger.info(f">>> KHỞI CHẠY MỞ RỘNG TOÀN CẦU YAHOO FINANCE (TỪ NĂM {start_year}) <<<")
    logger.info("=========================================================================")

    con = duckdb.connect(db_path, read_only=False)
    try:
        init_global_equity_tables(con)

        # -------------------------------------------------------------------
        # PHẦN 1: HÀNG HÓA, NÔNG SẢN & CHỈ SỐ CHÂU Á -> core.market_index_daily
        # -------------------------------------------------------------------
        logger.info("\n--- [PHẦN 1] CÀO HÀNG HÓA, NÔNG SẢN & CHỈ SỐ CHÂU Á TỪ 2000 ---")
        macro_targets = ASIAN_INDICES + COMMODITIES_AG
        all_macro_bars = []
        for sym, name in macro_targets:
            bars = fetch_symbol_bars(sym, name, start_year=start_year)
            for b in bars:
                all_macro_bars.append({
                    "index_code": b["code"],
                    "date": b["date"],
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                    "fetched_at": b["fetched_at"]
                })

        if all_macro_bars:
            df_macro = pd.DataFrame(all_macro_bars)
            before_idx = con.execute("SELECT count(*) FROM core.market_index_daily").fetchone()[0]
            con.register("df_macro", df_macro)
            con.execute("""
                INSERT INTO core.market_index_daily
                SELECT * FROM df_macro
                ON CONFLICT (index_code, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    fetched_at = EXCLUDED.fetched_at
            """)
            con.unregister("df_macro")
            after_idx = con.execute("SELECT count(*) FROM core.market_index_daily").fetchone()[0]
            logger.info(f"[PHẦN 1 HOÀN TẤT] Thêm {after_idx - before_idx:,} phiên mới vào core.market_index_daily (Tổng hiện tại: {after_idx:,}).")

        # -------------------------------------------------------------------
        # PHẦN 2: MAGNIFICENT 7 TECH STOCKS -> core.market_global_equity_daily
        # -------------------------------------------------------------------
        logger.info("\n--- [PHẦN 2] CÀO CỔ PHIẾU CÔNG NGHỆ MỸ (MAGNIFICENT 7) TỪ 2000 ---")
        all_equity_bars = []
        for sym, name in MAG7_SYMBOLS:
            bars = fetch_symbol_bars(sym, name, start_year=start_year)
            for b in bars:
                all_equity_bars.append({
                    "symbol": b["code"],
                    "date": b["date"],
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                    "fetched_at": b["fetched_at"]
                })

        if all_equity_bars:
            df_equity = pd.DataFrame(all_equity_bars)
            # 1. Staging
            con.register("df_eq_stg", df_equity)
            con.execute("INSERT INTO staging.market_global_equity_daily SELECT * FROM df_eq_stg")
            con.unregister("df_eq_stg")

            # 2. Core
            before_eq = con.execute("SELECT count(*) FROM core.market_global_equity_daily").fetchone()[0]
            con.register("df_eq_core", df_equity)
            con.execute("""
                INSERT INTO core.market_global_equity_daily
                SELECT * FROM df_eq_core
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    fetched_at = EXCLUDED.fetched_at
            """)
            con.unregister("df_eq_core")
            after_eq = con.execute("SELECT count(*) FROM core.market_global_equity_daily").fetchone()[0]
            logger.info(f"[PHẦN 2 HOÀN TẤT] Thêm {after_eq - before_eq:,} phiên mới vào core.market_global_equity_daily (Tổng hiện tại: {after_eq:,}).")

    finally:
        con.close()


if __name__ == "__main__":
    run_global_expansion(start_year=2000)
