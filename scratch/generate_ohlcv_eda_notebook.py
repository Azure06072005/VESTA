import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

notebook_data = {
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# PHÂN TÍCH KHÁM PHÁ DỮ LIỆU CHUYÊN SÂU (EDA): OHLCV 1D & 1M\n",
    "## Khảo sát Cấu trúc Vi mô và Chất lượng Dữ liệu trên Cổ phiếu Mẫu (FPT)\n",
    "\n",
    "**Dự án:** VESTA - Vietnamese Equity Sentiment-Triggered Agent  \n",
    "**Mục tiêu phân hệ:** Data Quality & Preprocessing (Trước bước F101 Cross-Reference Validation)  \n",
    "**Mã khảo sát mẫu:** `FPT` (Công ty Cổ phần FPT - Mã cổ phiếu đầu ngành công nghệ, thanh khoản cao, lịch sử giao dịch liên tục từ 2006 đến 2026)\n",
    "\n",
    "---\n",
    "\n",
    "### Mục tiêu nghiên cứu:\n",
    "1. **Dữ liệu 1D (Daily):** Đánh giá tính toàn vẹn (missing dates, zero-volume/zero-price do ngày tạm ngừng giao dịch), phân phối lợi suất (fat tails, biên độ trần/sàn HOSE $\\pm 7\\%$) và cơ chế điều chỉnh giá (Raw vs Adjusted Close).\n",
    "2. **Dữ liệu 1M (Intraday Minute):** Kiểm tra chuỗi thời gian nến phút, phát hiện và phân tích hiện tượng **lệch múi giờ UTC vs UTC+7** từ nhà cung cấp dữ liệu, khảo sát quy luật thanh khoản hình chữ U (U-shaped intraday volume pattern) giữa các phiên ATO, liên tục và ATC."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1. Khởi tạo môi trường và nạp các thư viện phân tích định lượng\n",
    "import duckdb\n",
    "import pandas as pd\n",
    "import numpy as np\n",
    "import matplotlib.pyplot as plt\n",
    "import seaborn as sns\n",
    "from datetime import datetime, timedelta\n",
    "\n",
    "# Cấu hình hiển thị và giao diện biểu đồ chuyên nghiệp\n",
    "plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')\n",
    "plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']\n",
    "plt.rcParams['figure.figsize'] = (14, 6)\n",
    "plt.rcParams['figure.dpi'] = 120\n",
    "pd.set_option('display.max_columns', 20)\n",
    "pd.set_option('display.float_format', lambda x: '%.3f' % x)\n",
    "\n",
    "# Đường dẫn cơ sở dữ liệu DuckDB VESTA\n",
    "DB_PATH = '../../db/vesta_snapshot.duckdb'\n",
    "con = duckdb.connect(DB_PATH, read_only=True)\n",
    "print(\"✅ Đã kết nối thành công DuckDB:\", DB_PATH)"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN I: KHẢO SÁT CHUYÊN SÂU DỮ LIỆU DAILY OHLCV (1D)\n",
    "Trích xuất toàn bộ chuỗi giá hàng ngày của `FPT` từ bảng `core.market_ohlcv_daily`."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1.1 Tải toàn bộ chuỗi nến ngày 1D của FPT\n",
    "query_1d = \"\"\"\n",
    "    SELECT symbol, date, open, high, low, close, volume\n",
    "    FROM core.market_ohlcv_daily\n",
    "    WHERE symbol = 'FPT'\n",
    "    ORDER BY date ASC\n",
    "\"\"\"\n",
    "df_1d = con.execute(query_1d).fetchdf()\n",
    "df_1d['date'] = pd.to_datetime(df_1d['date'])\n",
    "df_1d = df_1d.set_index('date')\n",
    "\n",
    "print(f\"🔹 Tổng số phiên giao dịch 1D: {len(df_1d):,}\")\n",
    "print(f\"🔹 Khung thời gian: Từ {df_1d.index.min().strftime('%d/%m/%Y')} đến {df_1d.index.max().strftime('%d/%m/%Y')}\")\n",
    "display(df_1d.head(5))\n",
    "display(df_1d.tail(5))"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1.2 Thống kê mô tả (Descriptive Statistics) & Khảo sát Giá trị Rỗng/Dị thường\n",
    "desc = df_1d[['open', 'high', 'low', 'close', 'volume']].describe()\n",
    "print(\"=== BẢNG THỐNG KÊ MÔ TẢ FPT 1D ===\")\n",
    "display(desc)\n",
    "\n",
    "# Kiểm tra giá <= 0 và volume <= 0 (Dấu hiệu ngày tạm ngừng giao dịch)\n",
    "zero_price_cnt = (df_1d['close'] <= 0).sum()\n",
    "zero_vol_cnt = (df_1d['volume'] <= 0).sum()\n",
    "null_cnt = df_1d.isnull().sum()\n",
    "\n",
    "print(\"\\n=== KIỂM TOÁN CHẤT LƯỢNG NẾN 1D ===\")\n",
    "print(f\"- Số phiên có giá đóng cửa <= 0 : {zero_price_cnt}\")\n",
    "print(f\"- Số phiên có khối lượng volume <= 0 : {zero_vol_cnt}\")\n",
    "print(\"- Số lượng giá trị NULL từng cột:\")\n",
    "print(null_cnt)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1.3 Phân tích Lợi suất Hàng ngày (Daily Return) & Fat Tails\n",
    "df_1d['log_ret'] = np.log(df_1d['close'] / df_1d['close'].shift(1))\n",
    "df_1d['pct_ret'] = df_1d['close'].pct_change() * 100\n",
    "\n",
    "# Kiểm tra các phiên chạm trần/sàn biên độ HOSE (+-7%)\n",
    "ceiling_days = df_1d[df_1d['pct_ret'] >= 6.8]\n",
    "floor_days = df_1d[df_1d['pct_ret'] <= -6.8]\n",
    "extreme_days = df_1d[df_1d['pct_ret'].abs() > 15]  # Bất thường có thể do chia tách chưa điều chỉnh\n",
    "\n",
    "print(f\"- Số phiên tăng kịch trần (>= 6.8%): {len(ceiling_days)}\")\n",
    "print(f\"- Số phiên giảm kịch sàn (<= -6.8%): {len(floor_days)}\")\n",
    "print(f\"- Số phiên biến động cực đại (> 15% - dấu hiệu ngày GDKHQ chia thưởng/cổ tức lớn): {len(extreme_days)}\")\n",
    "if len(extreme_days) > 0:\n",
    "    display(extreme_days[['close', 'pct_ret', 'volume']].head(5))"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 1.4 Trực quan hóa Lịch sử Giá và Phân phối Lợi suất 1D FPT\n",
    "fig, axes = plt.subplots(2, 2, figsize=(16, 10))\n",
    "\n",
    "# Biểu đồ 1: Diễn biến Giá đóng cửa lịch sử\n",
    "axes[0, 0].plot(df_1d.index, df_1d['close'], color='#1f77b4', lw=1.5, label='FPT Raw Close')\n",
    "axes[0, 0].set_title('Diễn biến Giá Đóng cửa FPT (2006 - 2026)', fontsize=12, fontweight='bold')\n",
    "axes[0, 0].set_ylabel('Giá (VND)')\n",
    "axes[0, 0].legend()\n",
    "\n",
    "# Biểu đồ 2: Khối lượng Giao dịch (Volume)\n",
    "axes[0, 1].bar(df_1d.index, df_1d['volume'], color='#2ca02c', alpha=0.6, width=2, label='Volume')\n",
    "axes[0, 1].set_title('Khối lượng Khớp lệnh Hàng ngày (Shares)', fontsize=12, fontweight='bold')\n",
    "axes[0, 1].set_ylabel('Khối lượng')\n",
    "axes[0, 1].legend()\n",
    "\n",
    "# Biểu đồ 3: Phân phối Lợi suất hàng ngày (Histogram & KDE)\n",
    "ret_clean = df_1d['pct_ret'].dropna()\n",
    "sns.histplot(ret_clean, bins=100, kde=True, ax=axes[1, 0], color='#ff7f0e')\n",
    "axes[1, 0].axvline(0, color='gray', linestyle='--')\n",
    "axes[1, 0].axvline(7, color='green', linestyle=':', label='Trần HOSE (+7%)')\n",
    "axes[1, 0].axvline(-7, color='red', linestyle=':', label='Sàn HOSE (-7%)')\n",
    "axes[1, 0].set_title(f'Phân phối Lợi suất Hàng ngày (Skewness: {ret_clean.skew():.2f}, Kurtosis: {ret_clean.kurtosis():.2f})', fontsize=12, fontweight='bold')\n",
    "axes[1, 0].set_xlabel('Lợi suất (%)')\n",
    "axes[1, 0].legend()\n",
    "\n",
    "# Biểu đồ 4: Biến động Lăn 30 ngày (30-Day Rolling Annualized Volatility)\n",
    "rolling_vol = df_1d['log_ret'].rolling(30).std() * np.sqrt(252) * 100\n",
    "axes[1, 1].plot(df_1d.index, rolling_vol, color='#d62728', lw=1.2, label='30D Rolling Volatility (%)')\n",
    "axes[1, 1].set_title('Độ biến động Giá thường niên hóa (Rolling 30-Day Volatility)', fontsize=12, fontweight='bold')\n",
    "axes[1, 1].set_ylabel('Biến động (%)')\n",
    "axes[1, 1].legend()\n",
    "\n",
    "plt.tight_layout()\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN II: KHẢO SÁT CHUYÊN SÂU DỮ LIỆU INTRADAY NẾN PHÚT (1M)\n",
    "Trích xuất dữ liệu nến 1m của `FPT` từ bảng `core.market_ohlcv_1m`."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 2.1 Tải dữ liệu nến phút 1m của FPT\n",
    "query_1m = \"\"\"\n",
    "    SELECT symbol, time, open, high, low, close, volume\n",
    "    FROM core.market_ohlcv_1m\n",
    "    WHERE symbol = 'FPT'\n",
    "    ORDER BY time ASC\n",
    "\"\"\"\n",
    "df_1m = con.execute(query_1m).fetchdf()\n",
    "df_1m['time'] = pd.to_datetime(df_1m['time'])\n",
    "df_1m['hour'] = df_1m['time'].dt.hour\n",
    "df_1m['minute'] = df_1m['time'].dt.minute\n",
    "df_1m['date'] = df_1m['time'].dt.date\n",
    "\n",
    "print(f\"🔹 Tổng số nến 1M của FPT: {len(df_1m):,}\")\n",
    "print(f\"🔹 Khung thời gian: Từ {df_1m['time'].min()} đến {df_1m['time'].max()}\")\n",
    "display(df_1m.head(5))"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 2.2 KHẢO SÁT HIỆN TƯỢNG LỆCH MÚI GIỜ (UTC vs UTC+7) TRONG NẾN 1M\n",
    "# Thị trường chứng khoán Việt Nam mở cửa: 09:00 - 11:30 & 13:00 - 14:45 (GMT+7)\n",
    "# Tương đương giờ UTC: 02:00 - 04:30 & 06:00 - 07:45 (UTC)\n",
    "\n",
    "hour_counts = df_1m['hour'].value_counts().sort_index()\n",
    "print(\"=== PHÂN BỔ SỐ LƯỢNG NẾN THEO KHUNG GIỜ (HOUR OF DAY) ===\")\n",
    "for h, cnt in hour_counts.items():\n",
    "    tag = \"\"\n",
    "    if h in [9, 10, 11, 13, 14]:\n",
    "        tag = \"(Chuẩn giờ Việt Nam UTC+7)\"\n",
    "    elif h in [2, 3, 4, 6, 7]:\n",
    "        tag = \"(Giờ quốc tế UTC - Lệch 7 tiếng)\"\n",
    "    print(f\"Giờ {h:02d}:00 -> {cnt:6,d} nến  {tag}\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 2.3 Biểu đồ Phân tích Múi giờ & Chuẩn hóa UTC -> UTC+7\n",
    "fig, ax = plt.subplots(figsize=(12, 5))\n",
    "colors = ['#d62728' if h in [2,3,4,6,7] else '#1f77b4' for h in hour_counts.index]\n",
    "ax.bar(hour_counts.index, hour_counts.values, color=colors, edgecolor='black', alpha=0.8)\n",
    "ax.set_xticks(range(0, 24))\n",
    "ax.set_title('Phát hiện Lệch Múi giờ trong Nến 1M (Đỏ: Cụm nến UTC, Xanh: Cụm nến UTC+7)', fontsize=13, fontweight='bold')\n",
    "ax.set_xlabel('Giờ trong ngày (Hour)')\n",
    "ax.set_ylabel('Số lượng nến phút')\n",
    "ax.grid(True, linestyle='--', alpha=0.5)\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 2.4 Chuẩn hóa Múi giờ về 100% Giờ Việt Nam (UTC+7)\n",
    "def standardize_to_vietnam_time(df):\n",
    "    df_std = df.copy()\n",
    "    # Nếu giờ nằm trong khoảng UTC (2-7), ta cộng thêm 7 tiếng\n",
    "    mask_utc = df_std['hour'].between(2, 7)\n",
    "    df_std.loc[mask_utc, 'time'] = df_std.loc[mask_utc, 'time'] + pd.Timedelta(hours=7)\n",
    "    df_std['hour_vn'] = df_std['time'].dt.hour\n",
    "    df_std['minute_vn'] = df_std['time'].dt.minute\n",
    "    df_std['date_vn'] = df_std['time'].dt.date\n",
    "    return df_std\n",
    "\n",
    "df_1m_vn = standardize_to_vietnam_time(df_1m)\n",
    "hour_vn_counts = df_1m_vn['hour_vn'].value_counts().sort_index()\n",
    "print(\"=== PHÂN BỔ SAU KHI CHUẨN HÓA VỀ GIỜ VIỆT NAM (UTC+7) ===\")\n",
    "for h, cnt in hour_vn_counts.items():\n",
    "    print(f\"Giờ {h:02d}:00 -> {cnt:6,d} nến\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# 2.5 Khảo sát Thanh khoản Khối lượng Hình chữ U (U-Shaped Intraday Pattern)\n",
    "# Gom nhóm theo từng phút trong ngày giao dịch chuẩn\n",
    "df_1m_vn['time_str'] = df_1m_vn['time'].dt.strftime('%H:%M')\n",
    "intraday_vol = df_1m_vn.groupby('time_str')['volume'].mean().sort_index()\n",
    "\n",
    "# Lọc bỏ ngoài giờ hành chính\n",
    "valid_times = intraday_vol.index[(intraday_vol.index >= '09:00') & (intraday_vol.index <= '14:45')]\n",
    "intraday_vol_filtered = intraday_vol.loc[valid_times]\n",
    "\n",
    "fig, ax = plt.subplots(figsize=(15, 6))\n",
    "ax.plot(range(len(intraday_vol_filtered)), intraday_vol_filtered.values, color='#9467bd', lw=2)\n",
    "\n",
    "# Đánh dấu các mốc quan trọng\n",
    "tick_indices = [0, 15, 75, 149, 150, 240, 255]\n",
    "tick_indices = [i for i in tick_indices if i < len(intraday_vol_filtered)]\n",
    "ax.set_xticks(tick_indices)\n",
    "ax.set_xticklabels([intraday_vol_filtered.index[i] for i in tick_indices])\n",
    "\n",
    "ax.set_title('Quy luật Khối lượng Giao dịch Trong ngày (Intraday Volume Smile - FPT)', fontsize=13, fontweight='bold')\n",
    "ax.set_xlabel('Thời gian trong ngày (Giờ Việt Nam)')\n",
    "ax.set_ylabel('Khối lượng khớp lệnh trung bình mỗi phút (Shares)')\n",
    "ax.grid(True, linestyle='--', alpha=0.6)\n",
    "plt.show()"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "--- \n",
    "## PHẦN III: TỔNG KẾT PHÁT HIỆN & ĐỀ XUẤT CHO TẦNG TIỀN XỬ LÝ (F1XX)\n",
    "\n",
    "### 1. Các vấn đề cốt lõi phát hiện từ dữ liệu thực nghiệm:\n",
    "- **Dữ liệu 1D (Daily):**\n",
    "  * Tồn tại các phiên nến có `volume = 0` hoặc `close = 0` do cổ phiếu tạm ngừng giao dịch. Cần forward-fill giá đóng cửa và gắn nhãn cờ `is_trading_day = FALSE` để không làm méo mó các chỉ báo động lượng (RSI, Bollinger Bands, Moving Average).\n",
    "  * Cần có hệ chế độ giá kép (**Dual-Mode Pricing**): Giá raw (chưa điều chỉnh) cho phân tích vi mô khớp lệnh và Giá adjusted (CAF) cho tính toán lợi suất dài hạn và backtesting.\n",
    "\n",
    "- **Dữ liệu 1M (Intraday):**\n",
    "  * **Lệch múi giờ UTC vs UTC+7**: Hơn 50% số nến được crawl từ nguồn API biểu đồ đang mang múi giờ UTC (02:00 - 07:45). Khi gom dữ liệu cần chạy pipeline `standardize_to_vietnam_time` để đồng nhất 100% chuỗi thời gian về múi giờ Việt Nam.\n",
    "  * **Cấu trúc phiên**: Khối lượng tập trung đột biến ở phiên ATO (09:00 - 09:15) và phiên ATC (14:30 - 14:45), tạo hình chữ U điển hình. Trong các mô hình định lượng intraday, cần xử lý tách biệt phiên đóng cửa ATC để tránh tín hiệu nhiễu do thỏa thuận cuối phiên.\n",
    "\n",
    "### 2. Các Feature mới cần triển khai trước F101:\n",
    "1. `F095`: Đồng bộ dữ liệu OHLCV sàn và rổ nhóm (Exchanges & Group Rooms).\n",
    "2. `F096`: Làm sạch nến 1D số 0 và chuẩn hóa ngày ngừng giao dịch.\n",
    "3. `F097`: Chuẩn hóa đồng nhất múi giờ nến phút (1M Timezone Harmonization) về UTC+7.\n",
    "4. `F098`: Kiểm định động cơ điều chỉnh giá kép (Dual-Mode Pricing Engine Verification)."
   ]
  }
 ],
 "metadata": {
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}

output_path = "d:/VESTA/notebooks/ohlcv/01_ohlcv_1d_1m_sample_eda.ipynb"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(notebook_data, f, ensure_ascii=False, indent=1)

print(f"✅ Đã tạo thành công Notebook EDA tại: {output_path}")
