"""Phân hệ thu thập dữ liệu nến 1 phút (Intraday 1M) cho thị trường chứng khoán Việt Nam (F002b).

Lưu trữ chuyên biệt tại: db/vesta_intraday_1m.duckdb
Nguồn dữ liệu: VCI (Vietcap) gap-chart API với cơ chế phân trang count_back lùi thời gian.
Độ sâu dữ liệu: 3 năm liên tục (từ tháng 09/2023 đến hiện tại).

Chính sách cào an toàn (Safe Crawl Policy):
1. Tốc độ an toàn: Delay 0.5s giữa các trang và 0.8s giữa các mã để tuân thủ giới hạn Cloudflare/WAF của VCI và rate-limit quota của vnstock.
2. Tự phục hồi lỗi (Exponential Backoff): Tự động chờ 3s-6s-12s khi gặp timeout hoặc ngắt kết nối mạng.
3. Phân tầng ưu tiên thanh khoản: VN30 -> VN100 -> HOSE/HNX thanh khoản cao -> UPCOM.
4. Bỏ qua thông minh (Smart Skip): Tự động kiểm tra meta.crawl_progress_1m và bỏ qua các mã đã đạt chuẩn 3 năm.
5. Checkpoint nguyên tử: Ghi nhận trạng thái từng mã ngay sau khi hoàn tất, đảm bảo có thể dừng/chạy lại bất kỳ lúc nào.
"""
from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Dict, List, Optional

import sys
import pathlib

SRC_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import duckdb
import pandas as pd
import requests

from etl import db

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Cấu hình ngưỡng thời gian 3 năm
MIN_3Y_CUTOFF_DATE = "2023-09-15"
DEFAULT_COUNT_BACK = 15000  # Mỗi request lấy ~15.000 nến (~60 ngày giao dịch)
MAX_PAGES_PER_SYMBOL = 15   # 15 * 15.000 = 225.000 nến (vượt mức 185.000 nến của 3 năm)
MAX_RETRIES = 3             # Số lần thử lại tối đa khi gặp lỗi mạng/timeout

VIETCAP_GAP_CHART_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
DNSE_CHART_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://trading.vietcap.com.vn",
    "Referer": "https://trading.vietcap.com.vn/",
}


def fetch_vietcap_1m_direct(
    symbol: str,
    end_time: Optional[str] = None,
    count_back: int = DEFAULT_COUNT_BACK,
    timeout: int = 15,
) -> pd.DataFrame:
    """Tải trực tiếp nến 1 phút từ máy chủ Vietcap Trading (không qua SDK trung gian)."""
    to_ts = int(pd.to_datetime(end_time).timestamp()) if end_time else int(time.time())
    payload = {
        "timeFrame": "ONE_MINUTE",
        "symbols": [symbol.upper()],
        "to": to_ts,
        "countBack": count_back,
    }

    resp = requests.post(VIETCAP_GAP_CHART_URL, json=payload, headers=BROWSER_HEADERS, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"Vietcap API HTTP {resp.status_code}: {resp.text[:120]}")

    data = resp.json()
    if not data or not isinstance(data, list) or len(data) == 0:
        return pd.DataFrame()

    item = data[0]
    raw_times = item.get("t")
    if not raw_times or len(raw_times) == 0:
        return pd.DataFrame()

    df = pd.DataFrame({
        "symbol": symbol.upper(),
        "time": pd.to_datetime([int(x) for x in raw_times], unit="s"),
        "open": [float(x) for x in item["o"]],
        "high": [float(x) for x in item["h"]],
        "low": [float(x) for x in item["l"]],
        "close": [float(x) for x in item["c"]],
        "volume": [int(x) for x in item["v"]],
    })

    # Chuẩn hóa về đơn vị 1.000 VNĐ nếu raw Vietcap trả về đơn vị VNĐ (>1000)
    if df["open"].max() > 1000:
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c] / 1000.0

    return df.sort_values("time").reset_index(drop=True)


def fetch_dnse_1m_direct(
    symbol: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    timeout: int = 10,
) -> pd.DataFrame:
    """Tải trực tiếp nến 1 phút từ DNSE Entrade X API (Dự phòng Fallback cho 60 ngày gần nhất)."""
    to_ts = int(pd.to_datetime(end_time).timestamp()) if end_time else int(time.time())
    from_ts = int(pd.to_datetime(start_time).timestamp()) if start_time else (to_ts - 86400 * 30)

    params = {
        "from": from_ts,
        "to": to_ts,
        "symbol": symbol.upper(),
        "resolution": "1",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(DNSE_CHART_URL, params=params, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        return pd.DataFrame()

    data = resp.json()
    raw_times = data.get("t")
    if not raw_times or len(raw_times) == 0:
        return pd.DataFrame()

    df = pd.DataFrame({
        "symbol": symbol.upper(),
        "time": pd.to_datetime([int(x) for x in raw_times], unit="s"),
        "open": [float(x) for x in data["o"]],
        "high": [float(x) for x in data["h"]],
        "low": [float(x) for x in data["l"]],
        "close": [float(x) for x in data["c"]],
        "volume": [int(x) for x in data["v"]],
    })

    if df["open"].max() > 1000:
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c] / 1000.0

    return df.sort_values("time").reset_index(drop=True)


def fetch_1m_page(
    symbol: str,
    end_time: Optional[str] = None,
    count_back: int = DEFAULT_COUNT_BACK,
    source: str = "vci_direct",
    max_retries: int = MAX_RETRIES,
) -> pd.DataFrame:
    """Tải một trang nến 1 phút từ nguồn Vietcap Direct với cơ chế fallback sang DNSE Entrade."""
    # 1. Thử tải trực tiếp từ Vietcap với cơ chế Retry & Exponential Backoff
    for attempt in range(1, max_retries + 1):
        try:
            df = fetch_vietcap_1m_direct(symbol=symbol, end_time=end_time, count_back=count_back, timeout=12)
            if df is not None and not df.empty:
                return df
            # Nếu trả về rỗng không có lỗi mạng (đã chạm đáy dữ liệu)
            return pd.DataFrame()
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str or "timed out" in err_str:
                wait_time = 2.0 * (2 ** (attempt - 1))
                logger.warning(f"[{symbol}] Vietcap Direct Timeout tại mốc end={end_time} (Thử {attempt}/{max_retries}). Chờ {wait_time:.1f}s...")
                time.sleep(wait_time)
            elif "429" in err_str or "rate limit" in err_str:
                logger.warning(f"[{symbol}] Vietcap Rate Limit (429). Chờ 30s...")
                time.sleep(30.0)
            else:
                logger.warning(f"[{symbol}] Lỗi Vietcap Direct tại end={end_time} (lần {attempt}): {e}")
                time.sleep(1.5)

    # 2. Cơ chế Fallback sang DNSE Entrade nếu Vietcap tạm thời nghẽn
    # Lưu ý: DNSE chỉ lưu nến 1m trong vòng ~60 ngày gần nhất
    try:
        now_ts = int(time.time())
        target_ts = int(pd.to_datetime(end_time).timestamp()) if end_time else now_ts
        if (now_ts - target_ts) <= (86400 * 60):
            logger.info(f"[{symbol}] Kích hoạt Fallback sang DNSE Entrade API cho mốc {end_time}...")
            df_dnse = fetch_dnse_1m_direct(symbol=symbol, end_time=end_time)
            if df_dnse is not None and not df_dnse.empty:
                logger.info(f"[{symbol}] Fallback DNSE thành công: +{len(df_dnse):,} nến.")
                return df_dnse
    except Exception as ex_dnse:
        logger.warning(f"[{symbol}] Fallback DNSE không thành công: {ex_dnse}")

    return pd.DataFrame()


def validate_1m_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Kiểm tra tính hợp lệ hình học nến và loại bỏ các dòng lỗi."""
    if df is None or df.empty:
        return pd.DataFrame()

    valid_mask = (
        df["time"].notna()
        & (df["volume"] >= 0)
        & (df["low"] <= df["open"])
        & (df["low"] <= df["close"])
        & (df["close"] <= df["high"])
        & (df["open"] <= df["high"])
    )
    cleaned = df[valid_mask].drop_duplicates(subset=["symbol", "time"]).copy()
    cleaned["fetched_at"] = pd.Timestamp.now()
    return cleaned


def write_1m_bars(df: pd.DataFrame, con: duckdb.DuckDBPyConnection) -> int:
    """Ghi dữ liệu nến 1 phút vào bảng core.market_ohlcv_1m theo cơ chế INSERT OR IGNORE."""
    if df is None or df.empty:
        return 0

    cleaned = validate_1m_bars(df)
    if cleaned.empty:
        return 0

    con.register("df_1m_incoming", cleaned)
    try:
        before_count = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m").fetchone()[0]
        con.execute("""
            INSERT OR IGNORE INTO core.market_ohlcv_1m
            SELECT symbol, "time", open, high, low, "close", volume, fetched_at
            FROM df_1m_incoming;
        """)
        after_count = con.execute("SELECT COUNT(*) FROM core.market_ohlcv_1m").fetchone()[0]
        return after_count - before_count
    finally:
        con.unregister("df_1m_incoming")


def backfill_symbol_1m(
    symbol: str,
    con: Optional[duckdb.DuckDBPyConnection] = None,
    min_cutoff: str = MIN_3Y_CUTOFF_DATE,
    max_pages: int = MAX_PAGES_PER_SYMBOL,
    sleep_sec: float = 0.5,
) -> Dict[str, Any]:
    """Cào bù toàn bộ lịch sử 3 năm nến 1 phút cho một mã cổ phiếu.

    Thực hiện phân trang lùi thời gian cho đến khi chạm mốc min_cutoff
    (tháng 09/2023) hoặc API không còn dữ liệu cũ hơn.
    """
    close_con = False
    if con is None:
        con = db.connect_intraday()
        close_con = True

    try:
        # Kiểm tra dữ liệu hiện tại trong DB
        existing = con.execute("""
            SELECT MIN(time), MAX(time), COUNT(*), COUNT(DISTINCT CAST(time AS DATE))
            FROM core.market_ohlcv_1m
            WHERE symbol = ?
        """, [symbol]).fetchone()

        cur_min, cur_max, cur_count, cur_days = existing

        # Nếu mốc sớm nhất đã đạt chuẩn 3 năm và có đủ lịch sử, bỏ qua
        if cur_min is not None and str(cur_min) <= min_cutoff and cur_days >= 650:
            logger.info(f"[{symbol}] Đã có đầy đủ 3 năm lịch sử ({cur_count:,} nến, {cur_days} ngày, từ {cur_min}). Bỏ qua!")
            _update_progress(con, symbol, cur_min, cur_max, cur_count, cur_days, True, "up_to_date")
            return {
                "symbol": symbol,
                "new_bars": 0,
                "total_bars": cur_count,
                "earliest": cur_min,
                "latest": cur_max,
                "is_complete_3y": True,
            }

        logger.info(f"[{symbol}] Hiện có: {cur_count or 0:,} nến ({cur_days or 0} ngày), từ {cur_min} đến {cur_max}")

        total_new_bars = 0
        current_end = str(cur_min) if cur_min is not None else None

        # Vòng lặp phân trang lùi thời gian
        for page in range(1, max_pages + 1):
            df_page = fetch_1m_page(symbol, end_time=current_end, count_back=DEFAULT_COUNT_BACK)
            if df_page.empty:
                logger.info(f"[{symbol}] Không còn dữ liệu cũ hơn tại mốc {current_end}.")
                break

            page_min = str(df_page["time"].min())
            page_max = str(df_page["time"].max())
            new_inserted = write_1m_bars(df_page, con)
            total_new_bars += new_inserted
            logger.info(f"[{symbol}] Trang {page}: Tải {len(df_page):,} nến ({page_min} -> {page_max}) | Thêm mới: {new_inserted:,}")

            # Điều kiện dừng: Đã chạm mốc cutoff 3 năm
            if page_min <= min_cutoff:
                logger.info(f"[{symbol}] Đã đạt mốc 3 năm ({page_min} <= {min_cutoff}). Hoàn tất phân trang.")
                break

            # Nếu trang trả về không lùi thêm thời gian
            if current_end is not None and page_min >= current_end:
                logger.info(f"[{symbol}] API chạm đáy lịch sử nến 1m. Hoàn tất.")
                break

            current_end = page_min
            time.sleep(sleep_sec)

        # Tính toán lại thông số tổng thể sau khi cào
        final_stat = con.execute("""
            SELECT MIN(time), MAX(time), COUNT(*), COUNT(DISTINCT CAST(time AS DATE))
            FROM core.market_ohlcv_1m
            WHERE symbol = ?
        """, [symbol]).fetchone()

        f_min, f_max, f_count, f_days = final_stat
        is_complete = (f_min is not None and str(f_min) <= "2023-10-01" and f_days >= 650)
        _update_progress(con, symbol, f_min, f_max, f_count, f_days, is_complete, "success")

        return {
            "symbol": symbol,
            "new_bars": total_new_bars,
            "total_bars": f_count,
            "earliest": f_min,
            "latest": f_max,
            "trading_days": f_days,
            "is_complete_3y": is_complete,
        }
    finally:
        if close_con:
            con.close()


def _update_progress(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
    earliest: Any,
    latest: Any,
    total_bars: int,
    trading_days: int,
    is_complete: bool,
    status: str,
) -> None:
    """Cập nhật trạng thái tiến độ cào vào meta.crawl_progress_1m."""
    con.execute("""
        INSERT INTO meta.crawl_progress_1m (
            symbol, earliest_time, latest_time, total_bars, trading_days, is_complete_3y, last_status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (symbol) DO UPDATE SET
            earliest_time = excluded.earliest_time,
            latest_time = excluded.latest_time,
            total_bars = excluded.total_bars,
            trading_days = excluded.trading_days,
            is_complete_3y = excluded.is_complete_3y,
            last_status = excluded.last_status,
            updated_at = excluded.updated_at;
    """, [symbol, earliest, latest, total_bars, trading_days, is_complete, status])


def get_vn30_symbols() -> List[str]:
    """Lấy danh sách mã VN30 từ cơ sở dữ liệu chính."""
    try:
        snap_con = db.connect(read_only=True)
        rows = snap_con.execute("""
            SELECT DISTINCT symbol FROM core.dim_index_constituents 
            WHERE index_code = 'VN30'
        """).fetchall()
        snap_con.close()
        if rows:
            return [r[0] for r in rows]
    except Exception:
        pass

    return [
        "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
        "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
        "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
    ]


def get_prioritized_symbols() -> List[str]:
    """Lấy danh sách toàn bộ mã cổ phiếu được sắp xếp theo thứ tự ưu tiên thanh khoản.

    Thứ tự:
    1. VN30 constituents.
    2. Các mã trong VN100 / VNDIAMOND / VNFINLEAD.
    3. Toàn bộ mã niêm yết HOSE và HNX.
    4. Các mã UPCOM và còn lại.
    """
    vn30 = set(get_vn30_symbols())
    index_syms = set()
    all_syms = []

    snap_con = None
    try:
        snap_con = db.connect(read_only=True)
        try:
            rows_idx = snap_con.execute("""
                SELECT DISTINCT symbol FROM core.dim_index_constituents
                WHERE index_code IN ('VN100', 'VNDIAMOND', 'VNFINLEAD', 'VNMID')
            """).fetchall()
            index_syms = {r[0] for r in rows_idx} - vn30
        except Exception:
            pass

        try:
            rows_all = snap_con.execute("""
                SELECT symbol, exchange FROM core.dim_symbol 
                ORDER BY CASE exchange WHEN 'HOSE' THEN 1 WHEN 'HNX' THEN 2 ELSE 3 END, symbol
            """).fetchall()
            all_syms = [r[0] for r in rows_all]
        except Exception:
            pass
    except Exception:
        pass
    finally:
        if snap_con is not None:
            try:
                snap_con.close()
            except Exception:
                pass

    if not all_syms:
        try:
            intra_con = db.connect_intraday(read_only=True)
            rows_intra = intra_con.execute("SELECT DISTINCT symbol FROM core.market_ohlcv_1m ORDER BY symbol").fetchall()
            all_syms = [r[0] for r in rows_intra]
            intra_con.close()
        except Exception:
            pass

    # Ghép theo thứ tự ưu tiên
    prioritized = []
    # Tier 1: VN30
    for s in sorted(vn30):
        if s in all_syms:
            prioritized.append(s)

    # Tier 2: VN100 / Major Indexes
    for s in sorted(index_syms):
        if s in all_syms and s not in prioritized:
            prioritized.append(s)

    # Tier 3: Phần còn lại
    for s in all_syms:
        if s not in prioritized:
            prioritized.append(s)

    return prioritized


def backfill_all_symbols(
    sleep_page: float = 0.5,
    sleep_symbol: float = 0.8,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Cào bù an toàn cho toàn bộ danh mục mã theo thứ tự ưu tiên thanh khoản.

    Tuân thủ chính sách Safe Crawl:
    - Bỏ qua mã đã có đủ 3 năm lịch sử.
    - Duy trì độ trễ an toàn giữa các request (0.5s trang, 0.8s mã).
    - Tự động lưu checkpoint sau từng mã.
    """
    symbols = get_prioritized_symbols()
    if limit is not None:
        symbols = symbols[:limit]

    logger.info("=" * 80)
    logger.info(f"KHỞI CHẠY TIẾN TRÌNH CÀO BÙ NẾN 1 PHÚT TOÀN THỊ TRƯỜNG ({len(symbols)} mã)")
    logger.info(f"Chính sách an toàn: Delay trang = {sleep_page}s | Delay mã = {sleep_symbol}s | Ngưỡng = {MIN_3Y_CUTOFF_DATE}")
    logger.info("=" * 80)

    con = db.connect_intraday()
    results = {}
    total_added_all = 0
    start_time = time.time()

    try:
        for idx, sym in enumerate(symbols, 1):
            logger.info(f"\n[{idx}/{len(symbols)}] Đang xử lý: {sym}...")
            res = backfill_symbol_1m(sym, con=con, sleep_sec=sleep_page)
            new_bars = res.get("new_bars", 0)
            total_added_all += new_bars
            results[sym] = res

            if new_bars > 0:
                logger.info(f"[+] {sym}: Đã nạp thêm +{new_bars:,} nến | Tổng: {res.get('total_bars', 0):,} | 3Y Complete: {res.get('is_complete_3y')}")
            else:
                logger.info(f"[=] {sym}: Đã cập nhật ({res.get('total_bars', 0):,} nến) | 3Y Complete: {res.get('is_complete_3y')}")

            time.sleep(sleep_symbol)
    finally:
        con.close()

    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info(f"HOÀN TẤT LƯỢT CÀO BÙ NẾN 1M TOÀN BỘ DANH MỤC TRONG {elapsed:.2f} GIÂY")
    logger.info(f"Tổng số nến mới đã thêm vào vesta_intraday_1m.duckdb: +{total_added_all:,} nến.")
    logger.info("=" * 80)

    return results


def backfill_vn30_universe() -> Dict[str, Any]:
    """Chạy cào bù toàn bộ lịch sử 3 năm nến 1 phút cho 30 mã VN30."""
    vn30 = get_vn30_symbols()
    logger.info(f"Bắt đầu cào bù dữ liệu nến 1m 3 năm cho VN30 ({len(vn30)} mã)...")

    con = db.connect_intraday()
    results = {}
    try:
        for idx, sym in enumerate(vn30, 1):
            logger.info(f"\n--- [{idx}/{len(vn30)}] Đang xử lý VN30: {sym} ---")
            res = backfill_symbol_1m(sym, con=con)
            results[sym] = res
            logger.info(f"[*] Kết quả {sym}: +{res.get('new_bars', 0):,} nến mới | Tổng: {res.get('total_bars', 0):,} nến | 3Y Complete: {res.get('is_complete_3y')}")
            time.sleep(0.8)
    finally:
        con.close()

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    backfill_all_symbols()
