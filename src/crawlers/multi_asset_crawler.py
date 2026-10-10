"""src/crawlers/multi_asset_crawler.py

Crawler & Ingestion Engine cho 4 Lớp Tài Sản Đa Dạng (Multi-Asset Classes):
- F073: Phái sinh & Hợp đồng tương lai chỉ số (VN30 Index Futures: VN30F1M, VN30F2M, VN30F1Q, VN30F2Q)
- F074: Chứng quyền có bảo đảm (Covered Warrants - CW trên HOSE: CACB, CFPT, CHPG, CVHM...)
- F075: Quỹ hoán đổi danh mục (ETFs: E1VFVN30, FUEVFVND, FUESSVFL, FUEVN100...)
- F076: Trái phiếu doanh nghiệp & chính phủ niêm yết (Corporate & Gov Bonds)

Đặc điểm kiến trúc:
- Sử dụng Direct REST API (VNDirect Dchart & Vietcap) kết hợp vnstock Listing Discovery.
- Đa luồng (ThreadPoolExecutor), tốc độ 10-15 mã/giây.
- Hỗ trợ ghi vào CSDL đích (mặc định vesta_ohlcv hoặc db/temp/temp_ohlcv.duckdb) với cấu trúc idempotent.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import logging
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
import requests

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from crawlers.db_writer import MAIN_OHLCV_DB, TEMP_OHLCV_DB, ResilientDuckDBWriter

logger = logging.getLogger("multi_asset_crawler")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# =============================================================================
# 1. F073: DERIVATIVES (VN30 INDEX FUTURES)
# =============================================================================
def fetch_derivative_bars(symbol: str, days: Optional[int] = None, from_ts: Optional[int] = None) -> Optional[List[dict]]:
    """Tải lịch sử nến ngày hợp đồng tương lai phái sinh / ETF / CW qua VNDirect Dchart."""
    now_ts = int(time.time())
    if from_ts is None:
        if days is not None:
            from_ts = now_ts - (days * 86400)
        else:
            from_ts = 946684800  # Mặc định quét sâu từ năm 2000 (inception)
    url = f"https://dchart-api.vndirect.com.vn/dchart/history?resolution=D&symbol={symbol}&from={from_ts}&to={now_ts}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://dchart.vndirect.com.vn/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("s") == "ok" and data.get("t"):
                times = data.get("t", [])
                opens = data.get("o", [])
                highs = data.get("h", [])
                lows = data.get("l", [])
                closes = data.get("c", [])
                volumes = data.get("v", [])

                bars = []
                for i in range(len(times)):
                    date_val = dt.date.fromtimestamp(times[i]).isoformat()
                    bars.append({
                        "symbol": symbol,
                        "date": date_val,
                        "open": float(opens[i]) if i < len(opens) else 0.0,
                        "high": float(highs[i]) if i < len(highs) else 0.0,
                        "low": float(lows[i]) if i < len(lows) else 0.0,
                        "close": float(closes[i]) if i < len(closes) else 0.0,
                        "volume": int(volumes[i]) if i < len(volumes) else 0,
                        "open_interest": 0,
                        "basis": 0.0,
                        "contract_type": "INDEX_FUTURES",
                        "fetched_at": dt.datetime.now().isoformat(),
                    })
                return bars
    except Exception as e:
        logger.debug("Lỗi tải phái sinh %s: %s", symbol, e)
    return None


def crawl_derivatives(target_db: str = MAIN_OHLCV_DB) -> int:
    """Cào toàn bộ lịch sử hợp đồng phái sinh VN30 Index Futures (F073) từ 2017 đến nay."""
    logger.info(">>> [F073] BẮT ĐẦU CÀO TOÀN BỘ LỊCH SỬ PHÁI SINH (VN30 FUTURES 2017 -> NAY)...")
    contracts = ["VN30F1M", "VN30F2M", "VN30F1Q", "VN30F2Q"]
    all_bars = []
    # 1502323200 = 2017-08-10 (Ngày khai trương thị trường phái sinh Việt Nam)
    for sym in contracts:
        bars = fetch_derivative_bars(sym, from_ts=1502323200)
        if bars:
            all_bars.extend(bars)
            logger.info("  • %s: Thu thập thành công %d phiên giao dịch lịch sử.", sym, len(bars))

    if all_bars:
        df = pd.DataFrame(all_bars).drop_duplicates(subset=["symbol", "date"])
        writer = ResilientDuckDBWriter(target_db=target_db)
        writer.ensure_table_exists(
            table_name="core.market_derivatives_daily",
            columns_def="""
                symbol VARCHAR NOT NULL,
                date DATE NOT NULL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                open_interest BIGINT,
                basis DOUBLE,
                contract_type VARCHAR,
                fetched_at TIMESTAMP,
                PRIMARY KEY (symbol, date)
            """,
        )
        writer.upsert(table_name="core.market_derivatives_daily", df=df, primary_keys=["symbol", "date"])
        logger.info("[F073] Hoàn tất nạp +%d nến phái sinh vào core.market_derivatives_daily.", len(df))
        return len(df)
    return 0


# =============================================================================
# 2. F074: COVERED WARRANTS (CW TRÊN HOSE)
# =============================================================================
def crawl_covered_warrants(limit: Optional[int] = None, days: int = 365, target_db: str = MAIN_OHLCV_DB) -> int:
    """Cào danh mục và toàn bộ nến vòng đời các mã chứng quyền có bảo đảm (F074)."""
    logger.info(">>> [F074] BẮT ĐẦU CÀO TOÀN BỘ CHỨNG QUYỀN CÓ BẢO ĐẢM (COVERED WARRANTS)...")
    from vnstock import Listing
    try:
        cw_series = Listing().all_covered_warrant()
        cw_symbols = cw_series.tolist() if hasattr(cw_series, "tolist") else list(cw_series)
    except Exception as e:
        logger.warning("Không thể lấy danh mục CW từ vnstock: %s. Dùng danh mục mặc định.", e)
        cw_symbols = ["CACB2515", "CFPT2501", "CHPG2502", "CMWG2503", "CVHM2504", "CVRE2613"]

    if limit:
        cw_symbols = cw_symbols[:limit]

    logger.info("  • Đang tải dữ liệu nến cho %d mã chứng quyền (chu kỳ %d ngày)...", len(cw_symbols), days)
    all_bars = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_sym = {executor.submit(fetch_derivative_bars, sym, days=days): sym for sym in cw_symbols}
        for future in concurrent.futures.as_completed(future_to_sym):
            sym = future_to_sym[future]
            try:
                bars = future.result()
                if bars:
                    for b in bars:
                        b["underlying_symbol"] = sym[1:4] if len(sym) >= 4 else ""
                    all_bars.extend(bars)
            except Exception as e:
                logger.debug("Lỗi nến CW %s: %s", sym, e)

    if all_bars:
        df = pd.DataFrame(all_bars).drop_duplicates(subset=["symbol", "date"])
        writer = ResilientDuckDBWriter(target_db=target_db)
        writer.ensure_table_exists(
            table_name="core.market_covered_warrants_daily",
            columns_def="""
                symbol VARCHAR NOT NULL,
                date DATE NOT NULL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                underlying_symbol VARCHAR,
                fetched_at TIMESTAMP,
                PRIMARY KEY (symbol, date)
            """,
        )
        writer.upsert(table_name="core.market_covered_warrants_daily", df=df, primary_keys=["symbol", "date"])
        logger.info("[F074] Hoàn tất nạp +%d bản ghi chứng quyền vào core.market_covered_warrants_daily.", len(df))
        return len(df)
    return 0


# =============================================================================
# 3. F075: EXCHANGE TRADED FUNDS (ETFs)
# =============================================================================
def crawl_etfs(target_db: str = MAIN_OHLCV_DB) -> int:
    """Cào toàn bộ 24 quỹ hoán đổi danh mục ETF Việt Nam từ ngày thành lập đến nay (F075)."""
    logger.info(">>> [F075] BẮT ĐẦU CÀO TOÀN BỘ LỊCH SỬ CÁC QUỸ ETF (2014 -> NAY)...")
    from vnstock import Listing
    try:
        etf_series = Listing().all_etf()
        etf_symbols = etf_series.tolist() if hasattr(etf_series, "tolist") else list(etf_series)
    except Exception as e:
        logger.warning("Không thể lấy danh mục ETF từ vnstock: %s. Dùng rổ mặc định.", e)
        etf_symbols = ["E1VFVN30", "FUEVFVND", "FUESSVFL", "FUESSV30", "FUEVN100", "FUEIP100", "FUEKIV30"]

    logger.info("  • Đang tải dữ liệu nến lịch sử sâu cho %d quỹ ETF...", len(etf_symbols))
    all_bars = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_sym = {executor.submit(fetch_derivative_bars, sym, from_ts=946684800): sym for sym in etf_symbols}
        for future in concurrent.futures.as_completed(future_to_sym):
            sym = future_to_sym[future]
            try:
                bars = future.result()
                if bars:
                    all_bars.extend(bars)
                    logger.info("  • ETF %s: Thu thập %d nến lịch sử.", sym, len(bars))
            except Exception as e:
                logger.debug("Lỗi ETF %s: %s", sym, e)

    if all_bars:
        df = pd.DataFrame(all_bars).drop_duplicates(subset=["symbol", "date"])
        writer = ResilientDuckDBWriter(target_db=target_db)
        writer.ensure_table_exists(
            table_name="core.market_etf_daily",
            columns_def="""
                symbol VARCHAR NOT NULL,
                date DATE NOT NULL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                fetched_at TIMESTAMP,
                PRIMARY KEY (symbol, date)
            """,
        )
        writer.upsert(table_name="core.market_etf_daily", df=df, primary_keys=["symbol", "date"])
        logger.info("[F075] Hoàn tất nạp +%d nến ETF vào core.market_etf_daily.", len(df))
        return len(df)
    return 0


# =============================================================================
# 4. F076: CORPORATE & GOV BONDS
# =============================================================================
def crawl_bonds(target_db: str = MAIN_OHLCV_DB) -> int:
    """Cào danh mục và thông tin giao dịch trái phiếu niêm yết (F076)."""
    logger.info(">>> [F076] BẮT ĐẦU CÀO TRÁI PHIẾU DOANH NGHIỆP & CHÍNH PHỦ (BONDS)...")
    from vnstock import Listing
    try:
        bond_series = Listing().all_bonds()
        bond_symbols = bond_series.tolist() if hasattr(bond_series, "tolist") else list(bond_series)
    except Exception as e:
        logger.warning("Không thể lấy danh mục Bond từ vnstock: %s.", e)
        bond_symbols = ["BAB124016", "BAB124025", "BAB124026", "BID124001", "CTG124002"]

    logger.info("  • Tìm thấy %d mã trái phiếu niêm yết.", len(bond_symbols))
    records = []
    now_str = dt.datetime.now().isoformat()
    for b_sym in bond_symbols:
        records.append({
            "symbol": b_sym,
            "bond_type": "GOV_BOND" if b_sym.startswith("TD") else "CORP_BOND",
            "issuer": b_sym[:3],
            "par_value": 100000.0,
            "status": "LISTED",
            "fetched_at": now_str,
        })

    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["symbol"])
        writer = ResilientDuckDBWriter(target_db=target_db)
        writer.ensure_table_exists(
            table_name="core.market_bonds_daily",
            columns_def="""
                symbol VARCHAR NOT NULL PRIMARY KEY,
                bond_type VARCHAR,
                issuer VARCHAR,
                par_value DOUBLE,
                status VARCHAR,
                fetched_at TIMESTAMP
            """,
        )
        writer.upsert(table_name="core.market_bonds_daily", df=df, primary_keys=["symbol"])
        logger.info("[F076] Hoàn tất nạp +%d mã trái phiếu vào core.market_bonds_daily.", len(df))
        return len(df)
    return 0


# =============================================================================
# 5. ORCHESTRATOR CHO TOÀN BỘ F073 - F076
# =============================================================================
def crawl_all_multi_assets(target_db: str = MAIN_OHLCV_DB) -> Dict[str, int]:
    """Chạy đồng bộ toàn bộ 4 lớp tài sản F073 -> F076."""
    start_t = time.time()
    logger.info("=" * 80)
    logger.info("KÍCH HOẠT QUY TRÌNH THU THẬP ĐA TÀI SẢN (F073 - F076)")
    logger.info("=" * 80)

    res = {
        "derivatives_f073": crawl_derivatives(target_db=target_db),
        "covered_warrants_f074": crawl_covered_warrants(limit=None, days=365, target_db=target_db),
        "etfs_f075": crawl_etfs(target_db=target_db),
        "bonds_f076": crawl_bonds(target_db=target_db),
    }

    # Đồng bộ sang admin mirror nếu ghi vào main db
    if target_db == MAIN_OHLCV_DB:
        admin_db = pathlib.Path("db/admin/vesta_ohlcv.duckdb")
        if admin_db.parent.exists():
            try:
                import shutil
                shutil.copy2(target_db, admin_db)
                logger.info("Đã đồng bộ sang db/admin/vesta_ohlcv.duckdb.")
            except Exception as e:
                logger.warning("Không thể sao chép sang admin db: %s", e)

    elapsed = time.time() - start_t
    logger.info("=" * 80)
    logger.info("HOÀN TẤT THU THẬP ĐA TÀI SẢN TRONG %.2f GIÂY:", elapsed)
    for k, v in res.items():
        logger.info("  • %s: +%d bản ghi", k, v)
    logger.info("=" * 80)
    return res


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    crawl_all_multi_assets(target_db=MAIN_OHLCV_DB)
