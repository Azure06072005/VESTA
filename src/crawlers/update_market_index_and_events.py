"""src/crawlers/update_market_index_and_events.py

Master Incremental Update Engine for:
1. db/vesta_market_index.duckdb:
   - core.market_foreign_flow_daily (2026-09-12 -> 2026-10-09 T-0)
   - core.market_breadth_series (2026-10-03 -> 2026-10-09 T-0)
   - core.market_sentiment_snapshot (2026-10-03 -> 2026-10-09 T-0)
   - core.market_global_equity_daily (2026-09-05 -> 2026-10-09 T-0)
2. Sync all updated databases to db/admin/ mirror.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import logging
import os
import pathlib
import re
import shutil
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
import requests

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from src.crawlers import market_insights

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("update_market_index")

MARKET_INDEX_DB = "db/vesta_market_index.duckdb"
ADMIN_MARKET_INDEX_DB = "db/admin/vesta_market_index.duckdb"


# =============================================================================
# 1. FOREIGN FLOW INCREMENTAL UPDATE (CAFEF API)
# =============================================================================
CAFEF_FF_URL = "https://cafef.vn/du-lieu/Ajax/PageNew/DataGDNN/GDNuocNgoai.ashx"
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://cafef.vn/du-lieu.chn",
}


def parse_cafef_date(date_str: str) -> Optional[dt.date]:
    match = re.search(r"/Date\((\d+)\)/", str(date_str))
    if match:
        ts = int(match.group(1)) / 1000.0
        return dt.datetime.fromtimestamp(ts).date()
    return None


def fetch_foreign_flow_single(trade_date: dt.date, exchange: str) -> List[Dict[str, Any]]:
    date_str = trade_date.strftime("%d/%m/%Y")
    url = f"{CAFEF_FF_URL}?TradeCenter={exchange}&Date={date_str}"
    rows = []
    now = dt.datetime.now()
    try:
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            items = data.get("Data", {}).get("ListDataNN", [])
            for it in items:
                sym = str(it.get("Symbol", "")).strip().upper()
                if not sym:
                    continue
                t_date = parse_cafef_date(it.get("TradeDate")) or trade_date
                rows.append({
                    "symbol": sym,
                    "date": t_date,
                    "buy_volume": float(it.get("BuyVolume", 0) or 0),
                    "sell_volume": float(it.get("SellVolume", 0) or 0),
                    "buy_value": float(it.get("BuyValue", 0) or 0),
                    "sell_value": float(it.get("SellValue", 0) or 0),
                    "net_volume": float(it.get("NetVolume", 0) or 0),
                    "net_value": float(it.get("NetValue", 0) or 0),
                    "foreign_room": float(it.get("Room", 0) or 0),
                    "fetched_at": now,
                })
    except Exception as e:
        logger.debug("Lỗi tải foreign flow %s %s: %s", exchange, date_str, e)
    return rows


def update_foreign_flow_all(start_date: str = "2026-09-12", end_date: str = "2026-10-09") -> int:
    """Cập nhật giao dịch khối ngoại từ start_date lên end_date cho 3 sàn."""
    logger.info(">>> [Foreign Flow] Bắt đầu cào dòng tiền ngoại từ %s đến %s (T-0)...", start_date, end_date)
    s_dt = dt.date.fromisoformat(start_date)
    e_dt = dt.date.fromisoformat(end_date)
    
    date_list = []
    curr = s_dt
    while curr <= e_dt:
        if curr.weekday() < 5:  # Chỉ lấy thứ 2 đến thứ 6
            date_list.append(curr)
        curr += dt.timedelta(days=1)

    exchanges = ["HOSE", "HASTC", "UPCOM"]
    all_rows = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = []
        for d in date_list:
            for ex in exchanges:
                futures.append(executor.submit(fetch_foreign_flow_single, d, ex))
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                all_rows.extend(res)

    if not all_rows:
        logger.warning("[Foreign Flow] Không có bản ghi mới.")
        return 0

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["symbol", "date"])
    logger.info("  ✓ Đã thu thập %d bản ghi khối ngoại mới. Đang nạp vào %s...", len(df), MARKET_INDEX_DB)
    
    con = duckdb.connect(MARKET_INDEX_DB)
    con.register("df_incoming_ff", df)
    con.execute("""
        DELETE FROM core.market_foreign_flow_daily
        WHERE (symbol, date) IN (SELECT symbol, date FROM df_incoming_ff);

        INSERT INTO core.market_foreign_flow_daily
        SELECT * FROM df_incoming_ff;
    """)
    cnt = con.execute("SELECT count(*), min(date), max(date) FROM core.market_foreign_flow_daily").fetchone()
    con.close()
    logger.info("  ✓ [Foreign Flow Xong] Tổng DB: %d dòng | Ngày: %s -> %s", cnt[0], cnt[1], cnt[2])
    return len(df)


# =============================================================================
# 2. MARKET BREADTH & SENTIMENT UPDATE
# =============================================================================
def update_breadth_and_sentiment() -> Tuple[int, int]:
    """Cập nhật độ rộng thị trường và chỉ số Fear & Greed lên T-0."""
    logger.info(">>> [Breadth & Sentiment] Bắt đầu cập nhật độ rộng và tâm lý thị trường lên T-0...")
    exchanges = ["HOSE", "HNX", "UPCOM"]
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    
    breadth_rows = []
    sentiment_rows = []
    
    for ex in exchanges:
        try:
            df_b = market_insights.fetch_market_breadth(exchange=ex, timeout=12)
            if not df_b.empty:
                for _, row in df_b.iterrows():
                    t_date = pd.to_datetime(row["trade_date"]).date()
                    if t_date >= dt.date(2026, 10, 1):
                        breadth_rows.append({
                            "exchange": ex,
                            "trade_date": t_date,
                            "pe": float(row["pe"]) if pd.notnull(row.get("pe")) else None,
                            "pb": float(row["pb"]) if pd.notnull(row.get("pb")) else None,
                            "above_ma20_pct": float(row["above_ma20_pct"]) if pd.notnull(row.get("above_ma20_pct")) else None,
                            "above_ma50_pct": float(row["above_ma50_pct"]) if pd.notnull(row.get("above_ma50_pct")) else None,
                            "above_ma200_pct": float(row["above_ma200_pct"]) if pd.notnull(row.get("above_ma200_pct")) else None,
                            "avg_20d_above_ma50_pct": float(row["avg_20d_above_ma50_pct"]) if pd.notnull(row.get("avg_20d_above_ma50_pct")) else None,
                            "position_line": float(row["position_line"]) if pd.notnull(row.get("position_line")) else None,
                            "close_index": float(row["close_index"]) if pd.notnull(row.get("close_index")) else None,
                            "source": "ASEAN_SC_DIRECT",
                            "fetched_at": now,
                        })
        except Exception as e:
            logger.debug("Lỗi breadth sàn %s: %s", ex, e)
            
        try:
            df_s = market_insights.fetch_market_fear_greed(exchange=ex, timeout=10)
            if not df_s.empty:
                row = df_s.iloc[0]
                clean_json = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
                sentiment_rows.append({
                    "exchange": ex,
                    "snapshot_date": today,
                    "fear_greed_score": float(row["fear_greed_score"]) if pd.notnull(row.get("fear_greed_score")) else None,
                    "advances": int(row["advances"]) if pd.notnull(row.get("advances")) else None,
                    "declines": int(row["declines"]) if pd.notnull(row.get("declines")) else None,
                    "no_change": int(row["no_change"]) if pd.notnull(row.get("no_change")) else None,
                    "mfi": float(row["mfi"]) if pd.notnull(row.get("mfi")) else None,
                    "rsi": float(row["rsi"]) if pd.notnull(row.get("rsi")) else None,
                    "index_change": float(row["index_change"]) if pd.notnull(row.get("index_change")) else None,
                    "volume_change": float(row["volume_change"]) if pd.notnull(row.get("volume_change")) else None,
                    "raw_json": json.dumps(clean_json, ensure_ascii=False, default=str),
                    "source": "ASEAN_SC_DIRECT",
                    "fetched_at": now,
                })
        except Exception as e:
            logger.debug("Lỗi sentiment sàn %s: %s", ex, e)

    con = duckdb.connect(MARKET_INDEX_DB)
    b_saved = 0
    s_saved = 0
    if breadth_rows:
        df_b_save = pd.DataFrame(breadth_rows).drop_duplicates(subset=["exchange", "trade_date"])
        con.register("df_b_save", df_b_save)
        con.execute("""
            DELETE FROM core.market_breadth_series
            WHERE (exchange, trade_date) IN (SELECT exchange, trade_date FROM df_b_save);

            INSERT INTO core.market_breadth_series
            SELECT * FROM df_b_save;
        """)
        b_saved = len(df_b_save)
        logger.info("  ✓ Đã cập nhật +%d dòng độ rộng thị trường (max date: %s)", b_saved, df_b_save["trade_date"].max())

    if sentiment_rows:
        df_s_save = pd.DataFrame(sentiment_rows).drop_duplicates(subset=["exchange", "snapshot_date"])
        con.register("df_s_save", df_s_save)
        con.execute("""
            DELETE FROM core.market_sentiment_snapshot
            WHERE (exchange, snapshot_date) IN (SELECT exchange, snapshot_date FROM df_s_save);

            INSERT INTO core.market_sentiment_snapshot
            SELECT * FROM df_s_save;
        """)
        s_saved = len(df_s_save)
        logger.info("  ✓ Đã cập nhật +%d dòng tâm lý Fear & Greed (max date: %s)", s_saved, today)

    con.close()
    return b_saved, s_saved


# =============================================================================
# 3. GLOBAL EQUITY LEADERS UPDATE (MAGNIFICENT 7 VIA YAHOO FINANCE)
# =============================================================================
MAG7_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


def update_global_equity_mag7() -> int:
    """Cập nhật 7 cổ phiếu công nghệ hàng đầu thế giới từ Yahoo Finance."""
    logger.info(">>> [Global Equity] Cập nhật nhóm Magnificent 7 (US Tech Leaders) lên T-0...")
    all_bars = []
    now = dt.datetime.now()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for sym in MAG7_TICKERS:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2mo"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                res = r.json().get("chart", {}).get("result", [])
                if res:
                    t_list = res[0].get("timestamp", [])
                    indicators = res[0].get("indicators", {}).get("quote", [{}])[0]
                    opens = indicators.get("open", [])
                    highs = indicators.get("high", [])
                    lows = indicators.get("low", [])
                    closes = indicators.get("close", [])
                    volumes = indicators.get("volume", [])
                    
                    for i in range(len(t_list)):
                        b_date = dt.date.fromtimestamp(t_list[i])
                        if b_date >= dt.date(2026, 9, 1):
                            all_bars.append({
                                "symbol": sym,
                                "date": b_date,
                                "open": float(opens[i]) if i < len(opens) and opens[i] is not None else 0.0,
                                "high": float(highs[i]) if i < len(highs) and highs[i] is not None else 0.0,
                                "low": float(lows[i]) if i < len(lows) and lows[i] is not None else 0.0,
                                "close": float(closes[i]) if i < len(closes) and closes[i] is not None else 0.0,
                                "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                                "fetched_at": now,
                            })
        except Exception as e:
            logger.debug("Lỗi Yahoo cho %s: %s", sym, e)

    if not all_bars:
        return 0

    df = pd.DataFrame(all_bars).drop_duplicates(subset=["symbol", "date"])
    con = duckdb.connect(MARKET_INDEX_DB)
    con.register("df_mag7", df)
    con.execute("""
        DELETE FROM core.market_global_equity_daily
        WHERE (symbol, date) IN (SELECT symbol, date FROM df_mag7);

        INSERT INTO core.market_global_equity_daily
        SELECT * FROM df_mag7;
    """)
    c_mag7 = con.execute("SELECT count(*), min(date), max(date) FROM core.market_global_equity_daily").fetchone()
    con.close()
    logger.info("  ✓ [Global Equity Xong] Tổng DB: %d dòng | Ngày: %s -> %s", c_mag7[0], c_mag7[1], c_mag7[2])
    return len(df)


# =============================================================================
# 4. MASTER RUNNER & SYNC TO ADMIN MIRROR
# =============================================================================
def run_all_updates():
    t_start = time.time()
    logger.info("=" * 80)
    logger.info("KHỞI CHẠY QUY TRÌNH CẬP NHẬT ĐỒNG BỘ TOÀN DIỆN LÊN T-0 (2026-10-09)")
    logger.info("=" * 80)

    # 1. Foreign Flow
    ff_cnt = update_foreign_flow_all(start_date="2026-09-12", end_date="2026-10-09")
    
    # 2. Breadth & Sentiment
    b_cnt, s_cnt = update_breadth_and_sentiment()
    
    # 3. Global Tech Leaders
    g_cnt = update_global_equity_mag7()

    # 4. Đồng bộ 4 database sang db/admin/
    admin_dir = pathlib.Path("db/admin")
    admin_dir.mkdir(parents=True, exist_ok=True)
    
    for db_file in ["vesta_market_index.duckdb", "vesta_events.duckdb", "vesta_news.duckdb", "vesta_fundamentals.duckdb", "vesta_ohlcv.duckdb"]:
        src_p = pathlib.Path("db") / db_file
        dst_p = admin_dir / db_file
        if src_p.exists():
            try:
                shutil.copy2(src_p, dst_p)
                logger.info("  ✓ Đã đồng bộ %s -> %s", src_p, dst_p)
            except Exception as e:
                logger.warning("Lỗi đồng bộ %s: %s", db_file, e)

    t_el = time.time() - t_start
    logger.info("=" * 80)
    logger.info("HOÀN TẤT ĐỒNG BỘ TOÀN DIỆN TRONG %.2f GIÂY:", t_el)
    logger.info("  • Foreign Flow mới     : +%d bản ghi (T-0 09/10/2026)", ff_cnt)
    logger.info("  • Market Breadth mới   : +%d bản ghi (T-0 09/10/2026)", b_cnt)
    logger.info("  • Market Sentiment mới : +%d bản ghi (T-0 09/10/2026)", s_cnt)
    logger.info("  • Global Mag7 Equity   : +%d bản ghi (T-0 08/10/2026)", g_cnt)
    logger.info("=" * 80)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    run_all_updates()
