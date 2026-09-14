"""scripts/fetch_vnstock_multiframe_data.py

Standalone script to fetch and aggregate multi-timeframe stock data from vnstock (Silver Tier):
1. Native Pre-aggregated OHLCV: 1m, 5m, 15m, 30m, 1H, 1D
2. High-Frequency Tick-by-Tick & Seconds OHLCV: 1s, 5s, 30s (via intraday tick resampling)
"""
import os
import sys
import pandas as pd

# Reconfigure stdout to UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# Try importing vnstock_data
try:
    from vnstock_data import Market
except ImportError:
    print("Vui lòng cài đặt vnstock_data hoặc kích hoạt môi trường ảo (.venv) có vnstock!")
    print("Lệnh: .venv\\Scripts\\python.exe scripts/fetch_vnstock_multiframe_data.py")
    sys.exit(1)


def fetch_native_ohlcv(symbol="FPT", interval="1m", length="1M"):
    """
    Cào nến OHLCV có sẵn trực tiếp từ API Vnstock.
    Hỗ trợ: '1m', '5m', '15m', '30m', '1H', '1D', '1W', '1M'
    """
    print(f"\n>>> [1] Đang cào nến OHLCV có sẵn từ API: Mã={symbol}, Khung={interval}, Độ dài={length}...")
    mkt = Market()
    try:
        df = mkt.equity(symbol).ohlcv(length=length, interval=interval)
        if df is not None and not df.empty:
            print(f" -> Thành công! Nhận được {len(df):,} nến {interval}.")
            print(df.head(5).to_string())
            return df
        else:
            print(" -> API trả về rỗng (0 dòng).")
            return None
    except Exception as e:
        print(f" -> Lỗi khi cào nến {interval}: {e}")
        return None


def fetch_seconds_bars_from_ticks(symbol="FPT", target_seconds=[1, 5, 30]):
    """
    Cào dữ liệu từng lệnh khớp (Tick-by-tick chính xác tới từng giây)
    và tự động đúc thành nến OHLCV theo khung giây: 1s, 5s, 30s.
    """
    print(f"\n>>> [2] Đang cào dữ liệu từng lệnh khớp (Tick-by-tick) cho mã {symbol}...")
    mkt = Market()
    try:
        df_ticks = mkt.equity(symbol).intraday()
        if df_ticks is None or df_ticks.empty:
            print(" -> Không có dữ liệu lệnh khớp trong phiên.")
            return {}
            
        print(f" -> Thành công! Nhận được {len(df_ticks):,} lệnh khớp với timestamp từng giây:")
        print(df_ticks.head(5).to_string())

        # Chuẩn hóa thời gian để resample
        df_ticks['time'] = pd.to_datetime(df_ticks['time'])
        df_ticks = df_ticks.sort_values('time').set_index('time')

        bars_dict = {}
        for sec in target_seconds:
            freq_str = f"{sec}s"
            # Đúc nến OHLC từ giá và tính tổng Volume khớp trong mỗi khung giây
            ohlc = df_ticks['price'].resample(freq_str).ohlc()
            vol = df_ticks['volume'].resample(freq_str).sum()
            bars = pd.concat([ohlc, vol], axis=1).dropna()
            
            print(f"\n -> Đã đúc thành công {len(bars):,} nến khung {sec} giây ({freq_str}):")
            print(bars.head(3).to_string())
            bars_dict[freq_str] = bars
            
        return bars_dict
    except Exception as e:
        print(f" -> Lỗi khi cào dữ liệu tick: {e}")
        return {}


if __name__ == "__main__":
    symbol_to_test = "FPT"
    
    print("=" * 80)
    print(f"BẮT ĐẦU CÀO DỮ LIỆU ĐA KHUNG THỜI GIAN (1S, 5S, 30S, 1M) - MÃ: {symbol_to_test}")
    print("=" * 80)

    # 1. Cào nến 1 phút có sẵn từ API
    df_1m = fetch_native_ohlcv(symbol=symbol_to_test, interval="1m", length="1M")

    # 2. Cào dữ liệu giây (1s, 5s, 30s) từ tick intraday
    bars_seconds = fetch_seconds_bars_from_ticks(symbol=symbol_to_test, target_seconds=[1, 5, 30])

    print("\n" + "=" * 80)
    print("TỔNG KẾT:")
    if df_1m is not None:
        print(f" - Khung 1 phút (1m) : CÓ HỖ TRỢ TRỰC TIẾP ({len(df_1m):,} nến)")
    if "1s" in bars_seconds:
        print(f" - Khung 1 giây (1s) : CÀO ĐƯỢC TỪ TICKS ({len(bars_seconds['1s']):,} nến)")
    if "5s" in bars_seconds:
        print(f" - Khung 5 giây (5s) : CÀO ĐƯỢC TỪ TICKS ({len(bars_seconds['5s']):,} nến)")
    if "30s" in bars_seconds:
        print(f" - Khung 30 giây (30s): CÀO ĐƯỢC TỪ TICKS ({len(bars_seconds['30s']):,} nến)")
    print("=" * 80)
